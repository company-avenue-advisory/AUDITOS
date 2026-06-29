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
from enum import Enum
from difflib import SequenceMatcher
import easyocr

# ────── Confidence Scoring for Bank Transactions ──────
class TransactionConfidence(Enum):
    SURE = "SURE"           # 95%+ confidence — table detection + all fields present
    PROBABLE = "PROBABLE"   # 70-95% confidence — fuzzy column match or regex with minor gaps
    UNCERTAIN = "UNCERTAIN" # <70% confidence — partial data, manual verification recommended

# ────── Bank Type Detection ──────
class BankTypeDetector:
    """Detects Indian bank type from PDF metadata and content patterns."""

    BANK_SIGNATURES = {
        "ICICI": ["Transactions at a Glance", "ICICI Bank", "Transaction Statement"],
        "HDFC": ["Transaction Statement", "HDFC Bank", "Account Statement"],
        "Axis": ["Transaction Details", "Axis Bank", "Account Transactions"],
        "Kotak": ["Transaction List", "Kotak Mahindra", "Transaction Report"],
        "SBI": ["SBI", "State Bank", "Transaction"],
        "CANARA": ["Canara Bank", "Account Statement"],
        "BOI": ["Bank of India", "Transaction Statement"],
        "PNB": ["Punjab National Bank", "Account Statement"],
        "UNION": ["Union Bank", "Transaction Statement"],
    }

    @staticmethod
    def detect(pdf_text: str) -> Tuple[str, float]:
        """
        Detect bank type from PDF text.
        Returns: (bank_name: str, confidence: float 0-1)
        """
        text_lower = pdf_text.lower()
        scores = {}

        for bank_name, signatures in BankTypeDetector.BANK_SIGNATURES.items():
            matches = sum(1 for sig in signatures if sig.lower() in text_lower)
            if matches > 0:
                scores[bank_name] = matches / len(signatures)

        if scores:
            best_bank = max(scores, key=scores.get)
            return best_bank, scores[best_bank]
        return "UNKNOWN", 0.0

# ────── Fuzzy Column Matcher ──────
def fuzzy_match(s1: str, s2: str, threshold: float = 0.6) -> bool:
    """
    Fuzzy string matching — returns True if similarity > threshold.
    """
    return SequenceMatcher(None, s1.lower(), s2.lower()).ratio() > threshold

# ────── Column Auto-Detector ──────
class ColumnDetector:
    """Intelligently maps table columns to transaction fields."""

    KEYWORDS = {
        "date": ["date", "trans date", "txn date", "posted date", "value date", "booking date"],
        "narration": ["narration", "description", "particulars", "remarks", "details", "reference", "transaction"],
        "debit": ["debit", "withdrawal", "withdraw", "dr", "deducted", "paid out"],
        "credit": ["credit", "deposit", "deposited", "cr", "received", "credited"],
        "balance": ["balance", "closing balance", "available balance", "running balance", "bal"],
        "cheque": ["cheque", "check", "chq", "cheque no"],
        "reference": ["reference", "ref no", "utr", "trace", "instrument"],
    }

    @staticmethod
    def detect_column_indices(header_row: List[str]) -> Dict[str, int]:
        """
        Maps header row to column indices using keyword matching.
        Returns dict: {"date": 0, "narration": 1, "debit": 2, "credit": 3, "balance": 4, ...}
        """
        result = {}
        header_lower = [h.lower().strip() for h in header_row]

        for field_name, keywords in ColumnDetector.KEYWORDS.items():
            for idx, header in enumerate(header_lower):
                # Exact or fuzzy match
                if any(kw in header or fuzzy_match(kw, header) for kw in keywords):
                    result[field_name] = idx
                    break

        return result

    @staticmethod
    def auto_map_columns(cols: List[str]) -> Dict[str, int]:
        """
        Fallback: if strict matching fails, assume positional order.
        Most banks use: Date, Narration, Debit, Credit, Balance
        """
        mapping = ColumnDetector.detect_column_indices(cols)

        # Fallback positional mapping
        if "date" not in mapping and len(cols) > 0:
            mapping["date"] = 0
        if "narration" not in mapping and len(cols) > 1:
            mapping["narration"] = 1
        if "debit" not in mapping and len(cols) > 2:
            mapping["debit"] = 2
        if "credit" not in mapping and len(cols) > 3:
            mapping["credit"] = 3
        if "balance" not in mapping and len(cols) > 4:
            mapping["balance"] = 4

        return mapping

# ────── Transaction Validator ──────
class TransactionValidator:
    """Validates extracted transactions and assigns confidence scores."""

    @staticmethod
    def is_valid_date(date_str: str) -> bool:
        """Check if date string is in recognizable format."""
        date_str = str(date_str).strip()
        if not date_str or date_str.lower() in ["nan", "none", ""]:
            return False
        # If extract_date_pattern could find it, it's valid
        return extract_date_pattern(date_str) is not None

    @staticmethod
    def is_valid_narration(narration: str) -> bool:
        """Check if narration is meaningful (not empty, not just whitespace)."""
        narration = str(narration).strip()
        return len(narration) > 0 and narration.lower() not in ["nan", "none", ""]

    @staticmethod
    def is_valid_amount(amount_str: str) -> bool:
        """Check if amount looks like a number."""
        amount_str = str(amount_str).strip()
        if amount_str.lower() in ["nan", "none", "", "0", "0.00"]:
            return False
        try:
            float(amount_str.replace(",", "").replace(" ", ""))
            return True
        except ValueError:
            return False

    @staticmethod
    def has_at_least_one_amount(debit: str, credit: str, balance: str) -> bool:
        """Must have at least one amount field."""
        return (
            TransactionValidator.is_valid_amount(debit) or
            TransactionValidator.is_valid_amount(credit) or
            TransactionValidator.is_valid_amount(balance)
        )

    @staticmethod
    def score_transaction(txn: Dict[str, Any]) -> TransactionConfidence:
        """
        Assign confidence score to a transaction.
        SURE: has date + narration + at least one amount (from table)
        PROBABLE: has date + amounts (fuzzy narration or regex extraction)
        UNCERTAIN: partial data or ambiguous
        """
        date_ok = TransactionValidator.is_valid_date(txn.get("date", ""))
        narration_ok = TransactionValidator.is_valid_narration(txn.get("narration", ""))
        has_amount = TransactionValidator.has_at_least_one_amount(
            txn.get("debit", ""),
            txn.get("credit", ""),
            txn.get("balance", "")
        )

        # Table detection (all fields present) → SURE
        if date_ok and narration_ok and has_amount:
            return TransactionConfidence.SURE

        # Regex fallback or fuzzy match → PROBABLE
        if date_ok and has_amount:
            return TransactionConfidence.PROBABLE

        # Partial data → UNCERTAIN
        if date_ok or has_amount:
            return TransactionConfidence.UNCERTAIN

        # Invalid
        return TransactionConfidence.UNCERTAIN

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

def parse_bank_statement(pdf_bytes: bytes, password: str = "", confidence_min: str = None) -> List[Dict[str, Any]]:
    """
    Multi-stage bank statement parser with confidence scoring.

    Stage 1: Detect bank type from PDF metadata
    Stage 2: Extract via table finder (fitz) with fuzzy column matching
    Stage 3: Fallback to regex extraction with right-to-left token parsing
    Stage 4: Validate each transaction and assign confidence score

    Returns list of dicts with fields:
      - date, narration, debit, credit, balance
      - confidence: "SURE", "PROBABLE", or "UNCERTAIN"
      - bank_detected: bank name
      - extraction_method: "table" or "regex"

    Args:
        pdf_bytes: PDF file bytes
        password: password for encrypted PDFs (optional)
        confidence_min: filter by confidence ("SURE", "PROBABLE", "UNCERTAIN"). None = no filter.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    if doc.is_encrypted:
        print("Document is encrypted. Authenticating...")
        authenticated = doc.authenticate(password)
        if not authenticated:
            raise ValueError("Invalid password for encrypted bank statement.")

    # Stage 1: Detect bank type
    first_page_text = doc[0].get_text() if len(doc) > 0 else ""
    bank_name, bank_confidence = BankTypeDetector.detect(first_page_text)
    print(f"[Bank Detection] {bank_name} (confidence: {bank_confidence:.2f})")

    transactions = []

    # Stage 2: Table Finder (Preferred — highest confidence)
    print("[Stage 2] Attempting table extraction...")
    table_count = 0
    for page_num in range(len(doc)):
        page = doc[page_num]
        tables = page.find_tables()
        table_count += len(tables)

        for table in tables:
            try:
                df = table.to_pandas()
                if df.empty or len(df) == 0:
                    continue

                # Auto-detect column indices using fuzzy matching
                header_row = [str(c).strip() for c in df.columns]
                col_mapping = ColumnDetector.auto_map_columns(header_row)

                date_idx = col_mapping.get("date", 0)
                narration_idx = col_mapping.get("narration", 1)
                debit_idx = col_mapping.get("debit", 2)
                credit_idx = col_mapping.get("credit", 3)
                balance_idx = col_mapping.get("balance", 4)

                for _, row in df.iterrows():
                    row_vals = [str(val).strip() for val in row.values]
                    if not row_vals or len(row_vals) < 2:
                        continue

                    raw_date = row_vals[date_idx] if date_idx < len(row_vals) else ""
                    date_val = extract_date_pattern(raw_date)
                    if not date_val:
                        continue

                    narration = row_vals[narration_idx] if narration_idx < len(row_vals) else ""
                    debit = row_vals[debit_idx] if debit_idx < len(row_vals) else ""
                    credit = row_vals[credit_idx] if credit_idx < len(row_vals) else ""
                    balance = row_vals[balance_idx] if balance_idx < len(row_vals) else ""

                    # Clean empty values
                    debit = debit if debit not in ["nan", "None", "0", "0.00", ""] else ""
                    credit = credit if credit not in ["nan", "None", "0", "0.00", ""] else ""
                    balance = balance if balance not in ["nan", "None", ""] else ""

                    txn = {
                        "date": date_val,
                        "narration": narration,
                        "debit": debit,
                        "credit": credit,
                        "balance": balance,
                        "bank_detected": bank_name,
                        "extraction_method": "table",
                    }

                    # Assign confidence
                    confidence = TransactionValidator.score_transaction(txn)
                    txn["confidence"] = confidence.value

                    transactions.append(txn)

            except Exception as e:
                print(f"  [Table parsing error on page {page_num}] {e}")
                continue

    print(f"  Extracted {len(transactions)} transactions from {table_count} table(s)")

    # Stage 3: Regex Fallback (if table extraction yielded nothing)
    if not transactions:
        print("[Stage 3] Table extraction found zero transactions. Initiating regex fallback...")

        for page_num in range(len(doc)):
            page = doc[page_num]
            text_layout = page.get_text("blocks")

            for block in text_layout:
                block_text = block[4]
                lines = block_text.split("\n")

                for line in lines:
                    line_clean = line.strip()
                    date_str = extract_date_pattern(line_clean)
                    if not date_str:
                        continue

                    line_without_date = line_clean.replace(date_str, "").strip()
                    tokens = line_without_date.split()

                    amounts = []
                    narration_tokens = []
                    popped_all_amounts = False

                    # Scan right-to-left for amounts
                    for tok in reversed(tokens):
                        tok_clean = tok.strip("crCRdrDR₹|")
                        if not popped_all_amounts and re.match(r"^[\-\+]?[\d,\.]+$", tok_clean) and any(
                            c.isdigit() for c in tok_clean
                        ):
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

                    txn = {
                        "date": date_str,
                        "narration": narration if narration else "BANK TRANSACTION",
                        "debit": debit,
                        "credit": credit,
                        "balance": balance,
                        "bank_detected": bank_name,
                        "extraction_method": "regex",
                    }

                    # Assign confidence (regex → lower confidence)
                    confidence = TransactionValidator.score_transaction(txn)
                    txn["confidence"] = confidence.value

                    transactions.append(txn)

        print(f"  Extracted {len(transactions)} transactions via regex fallback")

    # Stage 4: Filter by confidence (if requested)
    if confidence_min:
        original_count = len(transactions)
        transactions = [t for t in transactions if t["confidence"] == confidence_min]
        print(f"[Confidence Filter] {original_count} → {len(transactions)} (min: {confidence_min})")

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
