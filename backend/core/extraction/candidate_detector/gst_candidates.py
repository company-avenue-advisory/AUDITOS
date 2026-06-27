import re
from typing import List
from .candidate import Candidate

GSTIN_PATTERN = re.compile(r'\b\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}Z[A-Z\d]{1}\b')
PAN_PATTERN = re.compile(r'\b[A-Z]{5}\d{4}[A-Z]{1}\b')

def detect_gst_candidates(ocr_document) -> List[Candidate]:
    """
    Detects potential GSTIN and PAN candidates from the OCRDocument text.
    """
    candidates = []
    
    # Iterate through pages
    for page in ocr_document.pages:
        page_num = page.page_number
        lines = page.raw_text.split('\n')
        
        for line_idx, line in enumerate(lines):
            # Find GSTIN matches
            for match in GSTIN_PATTERN.finditer(line):
                gst_val = match.group(0)
                # Simple rule: if near "supplier" or "seller", raise confidence
                confidence = 0.8
                lower_line = line.lower()
                keyword = None
                if any(kw in lower_line for kw in ["supplier", "seller", "from", "vendor"]):
                    confidence = 0.95
                    keyword = "supplier"
                elif any(kw in lower_line for kw in ["buyer", "customer", "to", "recipient"]):
                    confidence = 0.9
                    keyword = "buyer"

                candidates.append(Candidate(
                    field="gstin",
                    value=gst_val,
                    page=page_num,
                    line=line_idx,
                    keyword=keyword,
                    method="regex",
                    confidence=confidence,
                    context=line.strip()
                ))

            # Find PAN matches
            for match in PAN_PATTERN.finditer(line):
                pan_val = match.group(0)
                # Ignore values if they match GSTIN segment to prevent duplicate scanning
                if any(pan_val in c.value for c in candidates if c.field == "gstin"):
                    continue
                confidence = 0.7
                candidates.append(Candidate(
                    field="pan",
                    value=pan_val,
                    page=page_num,
                    line=line_idx,
                    method="regex",
                    confidence=confidence,
                    context=line.strip()
                ))

    return candidates
