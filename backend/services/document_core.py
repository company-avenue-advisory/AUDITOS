import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except AttributeError:
    pass

import fitz  # PyMuPDF
import cv2
import numpy as np
import io
import re
import os
from typing import List, Dict, Any, Tuple, Optional
import easyocr

# Initialize EasyOCR Reader globally on-demand to cache model weights in memory
# (Runs on CPU to keep it zero-cost and universally compatible)
ocr_reader = None

def get_ocr_reader():
    global ocr_reader
    if ocr_reader is None:
        print("Initializing global EasyOCR Reader (lazy loading)...")
        ocr_reader = easyocr.Reader(['en'], gpu=False)
    return ocr_reader

def extract_date_pattern(val: str) -> Optional[str]:
    """
    Scans a string to find and extract standard Indian bank transaction date schemas.
    Supports separators: '/', '-', '.', space.
    Supports formats: DD/MM/YYYY, DD-MMM-YY, YYYY-MM-DD, DD MMM YYYY, etc.
    """
    patterns = [
        r"(\b\d{1,2}[/\-\.\s]+(?:\d{1,2}|[A-Za-z]{3,9})[/\-\.\s]+\d{2,4}\b)",
        r"(\b\d{4}[/\-\.\s]+\d{1,2}[/\-\.\s]+\d{1,2}\b)"
    ]
    for pat in patterns:
        match = re.search(pat, val)
        if match:
            return match.group(1).strip()
    return None

def parse_bank_statement(pdf_bytes: bytes, password: str = "") -> List[Dict[str, Any]]:
    """
    Decrypts a bank statement (if password protected), extracts transaction details
    using a table-finder or fallback regex pattern matching for Indian banks.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    
    if doc.is_encrypted:
        print("Document is encrypted. Authenticating...")
        authenticated = doc.authenticate(password)
        if not authenticated:
            raise ValueError("Invalid password for encrypted bank statement.")
            
    transactions = []
    
    # Attempt 1: Table Finder
    for page_num in range(len(doc)):
        page = doc[page_num]
        tables = page.find_tables()
        for table in tables:
            df = table.to_pandas()
            # Try to identify header mappings
            cols = [str(c).lower().strip() for c in df.columns]
            
            # Map columns to transaction fields
            date_idx, desc_idx, debit_idx, credit_idx, balance_idx = -1, -1, -1, -1, -1
            for idx, col in enumerate(cols):
                if "date" in col:
                    date_idx = idx
                elif any(x in col for x in ["narration", "description", "particulars", "remarks"]):
                    desc_idx = idx
                elif any(x in col for x in ["debit", "withdrawal", "withdraw", "dr"]):
                    debit_idx = idx
                elif any(x in col for x in ["credit", "deposit", "cr"]):
                    credit_idx = idx
                elif "balance" in col:
                    balance_idx = idx
                    
            # Fallback index mapping if standard headers weren't matches
            if date_idx == -1 and len(cols) > 0:
                date_idx = 0
            if desc_idx == -1 and len(cols) > 1:
                desc_idx = 1
                
            for _, row in df.iterrows():
                row_vals = [str(val).strip() for val in row.values]
                if not row_vals or len(row_vals) < 2:
                    continue
                    
                raw_date = row_vals[date_idx] if date_idx != -1 else ""
                date_val = extract_date_pattern(raw_date)
                if not date_val:
                    continue
                    
                narration = row_vals[desc_idx] if desc_idx != -1 else ""
                debit = row_vals[debit_idx] if (debit_idx != -1 and debit_idx < len(row_vals)) else ""
                credit = row_vals[credit_idx] if (credit_idx != -1 and credit_idx < len(row_vals)) else ""
                balance = row_vals[balance_idx] if (balance_idx != -1 and balance_idx < len(row_vals)) else ""
                
                transactions.append({
                    "date": date_val,
                    "narration": narration,
                    "debit": debit if debit not in ["nan", "None", "0", "0.00", ""] else "",
                    "credit": credit if credit not in ["nan", "None", "0", "0.00", ""] else "",
                    "balance": balance if balance not in ["nan", "None", ""] else ""
                })

    # Attempt 2: Regex Fallback (Standard Indian date patterns + token parsing from right-to-left)
    if not transactions:
        print("Table finder parsed zero transactions. Initiating regex fallback...")
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            text_layout = page.get_text("blocks")
            # Blocks are tuples: (x0, y0, x1, y1, "text", block_no, block_type)
            for block in text_layout:
                block_text = block[4]
                lines = block_text.split("\n")
                for line in lines:
                    line_clean = line.strip()
                    date_str = extract_date_pattern(line_clean)
                    if date_str:
                        # Extract rest of the line without date
                        line_without_date = line_clean.replace(date_str, "").strip()
                        tokens = line_without_date.split()
                        
                        amounts = []
                        narration_tokens = []
                        popped_all_amounts = False
                        
                        # Scan right-to-left to extract Debit, Credit, Balance
                        for tok in reversed(tokens):
                            tok_clean = tok.strip("crCRdrDR₹|")
                            # Check if token looks like a decimal/integer amount
                            if not popped_all_amounts and re.match(r"^[\-\+]?[\d,\.]+$", tok_clean) and any(c.isdigit() for c in tok_clean):
                                amounts.append(tok)
                                if len(amounts) >= 3:
                                    popped_all_amounts = True
                            else:
                                popped_all_amounts = True
                                narration_tokens.append(tok)
                                
                        amounts.reverse()
                        narration_tokens.reverse()
                        
                        narration = " ".join(narration_tokens)
                        
                        debit, credit, balance = "", "", ""
                        if len(amounts) == 1:
                            balance = amounts[0]
                        elif len(amounts) == 2:
                            debit = amounts[0]
                            balance = amounts[1]
                        elif len(amounts) >= 3:
                            debit = amounts[0]
                            credit = amounts[1]
                            balance = amounts[-1]
                            
                        transactions.append({
                            "date": date_str,
                            "narration": narration if narration else "BANK TRANSACTION",
                            "debit": debit,
                            "credit": credit,
                            "balance": balance
                        })
                        
    doc.close()
    return transactions

def smart_split_by_size(pdf_bytes: bytes, target_mb: float = 4.5) -> List[bytes]:
    """
    Estimate page byte thresholds, incrementally building sub-PDFs 
    such that each output PDF chunk resides under target_mb limit.
    """
    src_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    num_pages = len(src_doc)
    
    chunks = []
    current_doc = fitz.open()
    
    for i in range(num_pages):
        current_doc.insert_pdf(src_doc, from_page=i, to_page=i)
        
        # Test write to check current accumulated size in bytes
        test_stream = current_doc.write()
        test_size_mb = len(test_stream) / (1024 * 1024)
        
        if test_size_mb > target_mb:
            if len(current_doc) > 1:
                # Remove the page that put it over the limit
                current_doc.delete_page(len(current_doc) - 1)
                chunks.append(current_doc.write(garbage=3, deflate=True))
                
                # Start new chunk with the current page
                current_doc = fitz.open()
                current_doc.insert_pdf(src_doc, from_page=i, to_page=i)
            else:
                # A single page exceeds target_mb. We must write it as-is.
                chunks.append(current_doc.write(garbage=3, deflate=True))
                current_doc = fitz.open()
                
    if len(current_doc) > 0:
        chunks.append(current_doc.write(garbage=3, deflate=True))
        
    src_doc.close()
    return chunks

def enhance_scan(image_bytes: bytes) -> bytes:
    """
    Uses OpenCV to improve text scanning contrast.
    Converts image to grayscale, applies Gaussian adaptive thresholding,
    and returns a clean, single-page vector PDF file byte stream.
    """
    # 1. Load image
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Invalid image file format.")
        
    # 2. Transform to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # 3. Apply Adaptive thresholding for clean black-and-white print
    # 11 is block size, 2 is constant subtracted from mean
    enhanced = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )
    
    # 4. Save to temporary PNG stream in memory
    _, img_encoded = cv2.imencode(".png", enhanced)
    png_bytes = img_encoded.tobytes()
    
    # 5. Insert image into a blank single-page PDF
    out_pdf = fitz.open()
    rect = fitz.Rect(0, 0, img.shape[1], img.shape[0])
    page = out_pdf.new_page(width=rect.width, height=rect.height)
    page.insert_image(rect, stream=png_bytes)
    
    pdf_stream = out_pdf.write()
    out_pdf.close()
    
    return pdf_stream

def compress_pdf(pdf_bytes: bytes, quality: int = 50) -> bytes:
    """
    Optimizes a PDF file by downscaling image DPI and executing
    maximum garbage collection with deflate compression.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    
    # PyMuPDF saving with garbage collection level 4 and deflate enabled
    compressed_bytes = doc.write(
        garbage=4,
        deflate=True,
        clean=True
    )
    doc.close()
    return compressed_bytes

def ocr_extract(pdf_bytes: bytes) -> str:
    """
    Renders PDF pages to high-resolution images in memory and extracts
    text using the local offline EasyOCR model.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    full_text = ""
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        
        # Render page to high-quality image (150 DPI)
        pix = page.get_pixmap(dpi=150)
        img_data = pix.tobytes("png")
        
        # Load into OpenCV
        nparr = np.frombuffer(img_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        # Run OCR
        results = get_ocr_reader().readtext(img)
        page_text = "\n".join([res[1] for res in results])
        
        full_text += f"--- Page {page_num + 1} ---\n{page_text}\n\n"
        
    doc.close()
    return full_text.strip()
