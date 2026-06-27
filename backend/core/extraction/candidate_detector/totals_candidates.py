import re
from typing import List
from .candidate import Candidate

TOTAL_KEYWORDS = ["total", "subtotal", "sub-total", "grand total", "net amount", "invoice value", "round off", "rounded"]

def detect_totals_candidates(ocr_document) -> List[Candidate]:
    """
    Finds potential subtotal, grand total, and round off candidate values.
    """
    candidates = []
    
    for page in ocr_document.pages:
        page_num = page.page_number
        lines = page.raw_text.split('\n')
        
        for line_idx, line in enumerate(lines):
            lower_line = line.lower()
            for kw in TOTAL_KEYWORDS:
                if kw in lower_line:
                    # Look for decimal numbers
                    decimals = re.findall(r'\b\d{1,3}(?:,\d{3})*\.\d{2}\b|\b\d+\.\d{2}\b', line)
                    for dec in decimals:
                        clean_dec = dec.replace(',', '')
                        try:
                            val_float = float(clean_dec)
                        except ValueError:
                            continue
                        
                        field_name = "grand_total"
                        if "subtotal" in kw or "sub-total" in kw:
                            field_name = "subtotal"
                        elif "round" in kw:
                            field_name = "round_off"
                        elif "grand" in kw or "value" in kw:
                            field_name = "grand_total"

                        candidates.append(Candidate(
                            field=field_name,
                            value=val_float,
                            page=page_num,
                            line=line_idx,
                            keyword=kw,
                            method="totals_regex",
                            confidence=0.8,
                            context=line.strip()
                        ))
    return candidates
