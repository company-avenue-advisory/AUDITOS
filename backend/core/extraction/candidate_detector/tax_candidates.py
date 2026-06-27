import re
from typing import List
from .candidate import Candidate

TAX_KEYWORDS = ["cgst", "sgst", "igst", "cess", "gst rate", "tax amount"]

def detect_tax_candidates(ocr_document) -> List[Candidate]:
    """
    Scans the OCRDocument to find candidates related to CGST, SGST, IGST, and CESS tax values.
    """
    candidates = []
    
    for page in ocr_document.pages:
        page_num = page.page_number
        lines = page.raw_text.split('\n')
        
        for line_idx, line in enumerate(lines):
            lower_line = line.lower()
            for kw in TAX_KEYWORDS:
                if kw in lower_line:
                    # Find numerical values in the line (decimal numbers or rates)
                    numbers = re.findall(r'\b\d+\.\d{2}\b|\b\d+%\b', line)
                    for num in numbers:
                        val = num.replace('%', '')
                        try:
                            val_float = float(val)
                        except ValueError:
                            continue
                        
                        field_name = "tax_amount"
                        if "cgst" in kw:
                            field_name = "cgst"
                        elif "sgst" in kw:
                            field_name = "sgst"
                        elif "igst" in kw:
                            field_name = "igst"
                        elif "cess" in kw:
                            field_name = "cess"
                        elif "rate" in kw:
                            field_name = "gst_rate"

                        candidates.append(Candidate(
                            field=field_name,
                            value=val_float,
                            page=page_num,
                            line=line_idx,
                            keyword=kw,
                            method="tax_regex",
                            confidence=0.75,
                            context=line.strip()
                        ))
    return candidates
