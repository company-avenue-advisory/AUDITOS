import re
from typing import List
from .candidate import Candidate

INV_KEYWORDS = ["invoice no", "invoice number", "inv no", "invoice #", "bill no", "voucher no"]

def detect_invoice_number_candidates(ocr_document) -> List[Candidate]:
    """
    Scans for potential invoice number candidates by locating invoice keywords
    and parsing nearby alphanumeric tokens.
    """
    candidates = []
    
    for page in ocr_document.pages:
        page_num = page.page_number
        lines = page.raw_text.split('\n')
        
        for line_idx, line in enumerate(lines):
            lower_line = line.lower()
            for kw in INV_KEYWORDS:
                match = re.search(re.escape(kw), line, re.IGNORECASE)
                if match:
                    # Extract string following keyword
                    start_idx = match.end()
                    suffix = line[start_idx:].strip()
                    # Clean up punctuation at the start
                    suffix = re.sub(r'^[:\-\s#]+', '', suffix)
                    # Extract the first alphanumeric token (often invoice number)
                    token_match = re.match(r'^([a-zA-Z0-9/\-_]+)', suffix)
                    if token_match:
                        val = token_match.group(1).strip()
                        if len(val) >= 3:
                            candidates.append(Candidate(
                                field="invoice_number",
                                value=val,
                                page=page_num,
                                line=line_idx,
                                keyword=kw,
                                method="keyword_regex",
                                confidence=0.85,
                                context=line.strip()
                            ))
    return candidates
