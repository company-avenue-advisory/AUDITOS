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
import time
from typing import List, Dict, Any, Tuple, Optional
from enum import Enum
from difflib import SequenceMatcher

# ────── Configuration & Limits ──────
MAX_PDF_SIZE_MB = 50  # Max file size for bank statements
MAX_EXTRACTION_TIME_SEC = 120  # Max time to extract from one PDF
SAFE_FILENAME_CHARS = re.compile(r'[^a-zA-Z0-9._\-]')

# ────── Input Validation ──────
class DocumentValidationError(Exception):
    """Raised when document validation fails."""
    pass

def validate_pdf_input(pdf_bytes: bytes, filename: str = "document.pdf") -> None:
    """
    Validates PDF input for security and format compliance.

    Raises:
        DocumentValidationError: if validation fails
    """
    # Check file size
    size_mb = len(pdf_bytes) / (1024 * 1024)
    if size_mb > MAX_PDF_SIZE_MB:
        raise DocumentValidationError(
            f"File too large: {size_mb:.1f}MB exceeds limit of {MAX_PDF_SIZE_MB}MB. "
            f"Use Portal Splitter to chunk the file."
        )

    if size_mb < 0.01:
        raise DocumentValidationError("File is too small (<10KB) — not a valid PDF.")

    # Check PDF magic bytes
    if not pdf_bytes.startswith(b'%PDF'):
        raise DocumentValidationError("Invalid PDF format: file does not start with PDF magic bytes.")

    # Safe filename (prevent path traversal)
    if filename and '..' in filename or '/' in filename or '\\' in filename:
        raise DocumentValidationError("Invalid filename: contains path separators.")

def sanitize_text(text: str, max_length: int = 500) -> str:
    """
    Sanitizes transaction narrative/description text.
    - Removes control characters and excessive whitespace
    - Truncates to max_length to prevent CSV/Excel issues
    - Safe for CSV/JSON serialization
    """
    if not text:
        return ""

    # Remove control characters (except newline, tab)
    text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', str(text))

    # Collapse multiple spaces/tabs to single space
    text = re.sub(r'\s+', ' ', text).strip()

    # Truncate to safe length
    if len(text) > max_length:
        text = text[:max_length] + "..."

    return text

def sanitize_amount(amount_str: str) -> str:
    """
    Sanitizes numeric amount fields.
    Returns clean decimal number or empty string.
    """
    if not amount_str:
        return ""

    amount_str = str(amount_str).strip()

    # Remove common currency symbols and markers
    amount_str = re.sub(r'[₹$€£¥\s]', '', amount_str)

    # Allow only digits, commas, decimal point, minus sign
    if not re.match(r'^[\-]?[\d,]*\.?\d+$', amount_str):
        return ""

    # Normalize: remove commas, validate it's a valid number
    try:
        normalized = amount_str.replace(',', '')
        float(normalized)  # Validation check
        return normalized
    except ValueError:
        return ""

def sanitize_date(date_str: str) -> str:
    """
    Sanitizes date field — already extracted by extract_date_pattern,
    but apply final cleanup.
    """
    if not date_str:
        return ""

    # Remove control chars
    date_str = re.sub(r'[\x00-\x1F\x7F]', '', str(date_str)).strip()

    # Truncate to reasonable length (dates are max ~20 chars)
    if len(date_str) > 30:
        return ""

    return date_str

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
        import easyocr  # optional dependency (see requirements.txt) — import only when Tier 3 OCR is actually used
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

    Stage 0: Validate input (file size, format, encryption)
    Stage 1: Detect bank type from PDF metadata
    Stage 2: Extract via table finder (fitz) with fuzzy column matching
    Stage 3: Fallback to regex extraction with right-to-left token parsing
    Stage 4: Validate each transaction and assign confidence score
    Stage 5: Sanitize output (clean text, amounts, dates)

    Returns list of dicts with fields:
      - date, narration, debit, credit, balance
      - confidence: "SURE", "PROBABLE", or "UNCERTAIN"
      - bank_detected: bank name
      - extraction_method: "table" or "regex"

    Args:
        pdf_bytes: PDF file bytes
        password: password for encrypted PDFs (optional)
        confidence_min: filter by confidence ("SURE", "PROBABLE", "UNCERTAIN"). None = no filter.

    Raises:
        DocumentValidationError: if input validation fails
        ValueError: if decryption fails
    """
    start_time = time.time()

    # Stage 0: Input Validation
    try:
        validate_pdf_input(pdf_bytes)
    except DocumentValidationError as e:
        print(f"[Validation Error] {str(e)}")
        raise

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
        tables = list(page.find_tables())  # Convert TableFinder to list
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

                    # Sanitize all fields
                    date_val = sanitize_date(date_val)
                    narration = sanitize_text(narration, max_length=300)
                    debit = sanitize_amount(debit)
                    credit = sanitize_amount(credit)
                    balance = sanitize_amount(balance)

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

                    # Sanitize all fields
                    date_str = sanitize_date(date_str)
                    narration = sanitize_text(narration or "BANK TRANSACTION", max_length=300)

                    debit, credit, balance = "", "", ""
                    if len(amounts) == 1:
                        balance = sanitize_amount(amounts[0])
                    elif len(amounts) == 2:
                        debit = sanitize_amount(amounts[0])
                        balance = sanitize_amount(amounts[1])
                    elif len(amounts) >= 3:
                        debit = sanitize_amount(amounts[0])
                        credit = sanitize_amount(amounts[1])
                        balance = sanitize_amount(amounts[-1])

                    txn = {
                        "date": date_str,
                        "narration": narration,
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

    # Performance logging
    elapsed = time.time() - start_time
    if elapsed > MAX_EXTRACTION_TIME_SEC:
        print(f"[Warning] Extraction took {elapsed:.1f}s (max: {MAX_EXTRACTION_TIME_SEC}s)")
    else:
        print(f"[Performance] Extracted {len(transactions)} transactions in {elapsed:.2f}s")

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
    and returns a clean, single-page PDF.

    Falls back to simple greyscale conversion if cv2 not available.

    Raises:
        DocumentValidationError: if image is invalid or cv2/PIL unavailable
    """
    try:
        # 1. Load image with OpenCV
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Could not decode image — unsupported format or corrupted file.")

        # 2. Transform to grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # 3. Apply Adaptive thresholding for clean black-and-white print
        # 11 is block size, 2 is constant subtracted from mean
        enhanced = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )

        # 4. Encode to PNG
        _, img_encoded = cv2.imencode(".png", enhanced)
        png_bytes = img_encoded.tobytes()

    except ImportError:
        raise DocumentValidationError(
            "OpenCV (cv2) not installed. Install via: pip install opencv-python-headless"
        )
    except Exception as e:
        print(f"[Scan Enhancer] OpenCV processing failed: {e}. Attempting PIL fallback...")
        # Fallback: use PIL for simple greyscale conversion
        try:
            from PIL import Image, ImageOps
            pil_img = Image.open(io.BytesIO(image_bytes))
            # Convert to greyscale and increase contrast
            pil_img = ImageOps.grayscale(pil_img)
            # Save to PNG bytes
            png_buffer = io.BytesIO()
            pil_img.save(png_buffer, format="PNG")
            png_bytes = png_buffer.getvalue()
            print("  ✓ Fallback to PIL succeeded")
        except Exception as pil_error:
            raise DocumentValidationError(
                f"Image processing failed: {str(e)}. "
                f"Install cv2 (opencv-python-headless) for better results."
            )

    # 5. Insert image into a blank single-page PDF
    try:
        out_pdf = fitz.open()
        # Estimate image dimensions from PNG
        from PIL import Image as PILImage
        pil_img_temp = PILImage.open(io.BytesIO(png_bytes))
        width, height = pil_img_temp.size
        rect = fitz.Rect(0, 0, width, height)
        page = out_pdf.new_page(width=width, height=height)
        page.insert_image(rect, stream=png_bytes)

        pdf_stream = out_pdf.write()
        out_pdf.close()

        return pdf_stream

    except Exception as e:
        raise DocumentValidationError(f"PDF generation failed: {str(e)}")

# ────── Tiered OCR System ──────
class OCRProvider:
    """Enum-like class for OCR providers."""
    PYMUPDF_TEXT = "pymupdf"      # Tier 1: Native text extraction (instant, no ML)
    TESSERACT = "tesseract"        # Tier 2: Lightweight CPU OCR
    EASYOCR = "easyocr"            # Tier 3: Heavyweight but accurate
    AUTO = "auto"                  # Try Tier 1 → Tier 2 → Tier 3

def is_tesseract_available() -> bool:
    """Check if tesseract-ocr is installed on the system."""
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False

def ocr_extract_pymupdf(pdf_bytes: bytes) -> str:
    """
    Tier 1 (Fastest): Extract text directly from PDF using PyMuPDF.
    Works on PDFs with embedded text layers (most modern PDFs).
    Returns: extracted text or empty string if no text found
    """
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        full_text = ""

        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text(option="text")
            if text.strip():
                full_text += f"--- Page {page_num + 1} ---\n{text}\n"

        doc.close()

        if full_text.strip():
            return full_text.strip()
        else:
            return ""  # Signal: no text found, try next tier

    except Exception as e:
        print(f"  [PyMuPDF] Text extraction failed: {e}")
        return ""

def ocr_extract_tesseract(pdf_bytes: bytes, timeout: int = 30) -> str:
    """
    Tier 2 (Medium): Lightweight Tesseract OCR via pytesseract.
    Good for scanned PDFs, CPU-only, ~1-2s per page.
    """
    try:
        import pytesseract
        from PIL import Image

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        full_text = ""

        for page_num in range(len(doc)):
            page = doc[page_num]

            # Render to image
            pix = page.get_pixmap(dpi=150)
            img_data = pix.tobytes("png")

            # Convert to PIL Image
            from io import BytesIO
            img = Image.open(BytesIO(img_data))

            # Run Tesseract with timeout
            try:
                text = pytesseract.image_to_string(img)
                if text.strip():
                    full_text += f"--- Page {page_num + 1} ---\n{text}\n"
            except Exception as e:
                print(f"  [Tesseract] Page {page_num + 1} failed: {e}")
                continue

        doc.close()
        return full_text.strip() if full_text.strip() else ""

    except ImportError:
        print("  [Tesseract] pytesseract not installed. Install via: pip install pytesseract")
        return ""
    except Exception as e:
        print(f"  [Tesseract] Error: {e}")
        return ""

def ocr_extract_easyocr(pdf_bytes: bytes, timeout: int = 90) -> str:
    """
    Tier 3 (Heavyweight): EasyOCR with GPU fallback to CPU.
    Best accuracy, ~2-5s per page, lazy-loaded.
    Wrapped in a ThreadPoolExecutor with a hard timeout to prevent hanging.
    """
    import concurrent.futures

    def _run_easyocr(pdf_bytes: bytes) -> str:
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            full_text = ""
            for page_num in range(len(doc)):
                page = doc[page_num]
                pix = page.get_pixmap(dpi=150)
                img_data = pix.tobytes("png")
                nparr = np.frombuffer(img_data, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if img is None:
                    print(f"  [EasyOCR] Page {page_num + 1}: failed to decode image")
                    continue
                try:
                    results = get_ocr_reader().readtext(img, detail=0)
                    page_text = "\n".join(results) if results else ""
                    if page_text.strip():
                        full_text += f"--- Page {page_num + 1} ---\n{page_text}\n"
                except Exception as e:
                    print(f"  [EasyOCR] Page {page_num + 1} failed: {e}")
                    continue
            doc.close()
            return full_text.strip()
        except Exception as e:
            print(f"  [EasyOCR] Error: {e}")
            return ""

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_run_easyocr, pdf_bytes)
            return future.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        print(f"  [EasyOCR] Timed out after {timeout}s — returning empty string.")
        return ""
    except Exception as e:
        print(f"  [EasyOCR] Unexpected error: {e}")
        return ""

def ocr_extract_with_fallback(pdf_bytes: bytes, provider: str = "auto") -> str:
    """
    Extract text from PDF with intelligent fallback chain.

    Provider priority:
      "auto": PyMuPDF → Tesseract (if available) → EasyOCR
      "pymupdf": PyMuPDF only
      "tesseract": Tesseract only (raises error if not available)
      "easyocr": EasyOCR only

    Returns: extracted text (may be empty if all tiers fail)
    """
    provider = provider.lower()

    # Tier 1: PyMuPDF (always try first in auto mode)
    if provider in ["auto", "pymupdf"]:
        print("[OCR] Tier 1: Trying PyMuPDF native text extraction...")
        text = ocr_extract_pymupdf(pdf_bytes)
        if text:
            print(f"  ✓ PyMuPDF succeeded ({len(text)} chars)")
            return text
        if provider == "pymupdf":
            print("  [PyMuPDF] No text found in PDF")
            return ""

    # Tier 2: Tesseract (if available)
    if provider in ["auto", "tesseract"]:
        if is_tesseract_available():
            print("[OCR] Tier 2: Trying Tesseract...")
            text = ocr_extract_tesseract(pdf_bytes)
            if text:
                print(f"  ✓ Tesseract succeeded ({len(text)} chars)")
                return text
        elif provider == "tesseract":
            raise RuntimeError(
                "Tesseract OCR requested but pytesseract not installed. "
                "Install via: pip install pytesseract"
            )

    # Tier 3: EasyOCR (fallback)
    if provider in ["auto", "easyocr"]:
        print("[OCR] Tier 3: Trying EasyOCR (may take 30-60s)...")
        text = ocr_extract_easyocr(pdf_bytes)
        if text:
            print(f"  ✓ EasyOCR succeeded ({len(text)} chars)")
            return text
        elif provider == "easyocr":
            raise RuntimeError("EasyOCR failed — PDF may be corrupted or unreadable")

    # All tiers failed
    if provider == "auto":
        raise RuntimeError(
            "All OCR tiers failed. PDF may be corrupted, encrypted, or contain no readable content. "
            "Try: 1) Upload a different PDF, 2) Use Scan Enhancer on scanned images first."
        )

    return ""

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

def ocr_extract(pdf_bytes: bytes, provider: str = "auto") -> str:
    """
    OCR extraction with tiered fallback (PyMuPDF → Tesseract → EasyOCR).
    When Celery is active and the document needs EasyOCR (heavy tier),
    dispatches to the dedicated 'ocr' Celery queue instead of running inline.
    """
    return ocr_extract_with_fallback(pdf_bytes, provider)


def ocr_extract_via_celery(pdf_bytes: bytes, provider: str = "auto", wait_timeout: int = 180) -> str:
    """
    Routes OCR to the dedicated Celery 'ocr' queue when Celery is active.
    Falls back to inline execution if Celery is unavailable.

    Use this from the Document Utilities endpoint so heavy OCR jobs don't
    tie up the FastAPI request thread.
    """
    broker_url = os.getenv("CELERY_BROKER_URL", "")
    if not broker_url:
        return ocr_extract(pdf_bytes, provider)

    try:
        import base64
        from celery_app import ocr_extract_task
        pdf_b64 = base64.b64encode(pdf_bytes).decode()
        result = ocr_extract_task.apply_async(
            args=[pdf_b64, provider],
            queue="ocr",
        )
        text = result.get(timeout=wait_timeout)
        return text or ""
    except Exception as e:
        print(f"[OCR Dispatch] Celery OCR task failed ({e}), running inline.")
        return ocr_extract(pdf_bytes, provider)
