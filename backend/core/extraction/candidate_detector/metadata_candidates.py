import re
from typing import List
from .candidate import Candidate

IFSC_PATTERN = re.compile(r'\b[A-Z]{4}0[A-Z0-9]{6}\b')
# Date pattern (supports DD/MM/YYYY, DD-MM-YYYY, DD-MMM-YYYY etc.)
DATE_PATTERN = re.compile(
    r'\b(?:\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})|(?:\d{1,2}[/\-\. ](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-zA-Z]*[/\-\. ]\d{2,4})\b',
    re.IGNORECASE
)

def detect_metadata_candidates(ocr_document) -> List[Candidate]:
    """
    Detects dates, bank accounts, and IFSC code candidate items.
    """
    candidates = []
    
    for page in ocr_document.pages:
        page_num = page.page_number
        lines = page.raw_text.split('\n')
        
        for line_idx, line in enumerate(lines):
            lower_line = line.lower()
            
            # IFSC detection
            for match in IFSC_PATTERN.finditer(line):
                ifsc = match.group(0)
                candidates.append(Candidate(
                    field="ifsc",
                    value=ifsc,
                    page=page_num,
                    line=line_idx,
                    method="regex",
                    confidence=0.9,
                    context=line.strip()
                ))
            
            # Date detection
            for match in DATE_PATTERN.finditer(line):
                date_val = match.group(0)
                # Determine field type: invoice_date or due_date
                field = "invoice_date"
                keyword = "date"
                if "due" in lower_line:
                    field = "due_date"
                    keyword = "due date"
                
                candidates.append(Candidate(
                    field=field,
                    value=date_val,
                    page=page_num,
                    line=line_idx,
                    keyword=keyword,
                    method="regex",
                    confidence=0.8,
                    context=line.strip()
                ))

            # Bank Account detection
            if "a/c" in lower_line or "account" in lower_line or "bank" in lower_line:
                # Look for long digits sequences (9 to 18 digits)
                ac_match = re.search(r'\b\d{9,18}\b', line)
                if ac_match:
                    ac_val = ac_match.group(0)
                    candidates.append(Candidate(
                        field="bank_account",
                        value=ac_val,
                        page=page_num,
                        line=line_idx,
                        keyword="account",
                        method="regex",
                        confidence=0.7,
                        context=line.strip()
                    ))
    return candidates
