import re
from typing import Dict, List, Any

class SemanticColumnClassifier:
    """
    Stage 1: Classifies detected table columns into semantic categories:
    HSN, DESCRIPTION, QTY, RATE, DISCOUNT, TAXABLE, CGST, SGST, IGST, TOTAL, OTHER
    """
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        # Define semantic matching patterns
        self.rules = {
            "HSN": r"\b(hsn|sac|hsn[-_\s]*code|sac[-_\s]*code)\b",
            "DESCRIPTION": r"\b(particulars|description|item|service|goods|product)\b",
            "QTY": r"\b(qty|quantity|units|nos|pcs|volume)\b",
            "RATE": r"\b(rate|price|unit[-_\s]*price|charges|val)\b",
            "DISCOUNT": r"\b(disc|discount|less|deduction)\b",
            "TAXABLE": r"\b(taxable|assessable|amount|value|taxable[-_\s]*value|net[-_\s]*amount)\b",
            "CGST": r"\b(cgst|central[-_\s]*gst|cgst[-_\s]*amount)\b",
            "SGST": r"\b(sgst|utgst|state[-_\s]*gst|sgst[-_\s]*amount)\b",
            "IGST": r"\b(igst|integrated[-_\s]*gst|igst[-_\s]*amount)\b",
            "TOTAL": r"\b(total|gross|net[-_\s]*total|final|total[-_\s]*amount)\b"
        }

    def classify_columns(self, headers: List[str]) -> Dict[str, str]:
        """
        Maps a list of raw column headers to their classified semantic labels.
        """
        mappings = {}
        for col_idx, header in enumerate(headers):
            header_lower = str(header).lower().strip()
            matched_label = "OTHER"
            
            for label, pattern in self.rules.items():
                if re.search(pattern, header_lower):
                    matched_label = label
                    break
            
            # Additional heuristic: if 'amount' is matched, refine based on tax terms
            if matched_label == "TAXABLE" and (any(t in header_lower for t in ["cgst", "sgst", "igst"]) or ("tax" in header_lower and "taxable" not in header_lower)):
                if "cgst" in header_lower:
                    matched_label = "CGST"
                elif "sgst" in header_lower or "utgst" in header_lower:
                    matched_label = "SGST"
                elif "igst" in header_lower:
                    matched_label = "IGST"
                else:
                    matched_label = "TOTAL"
                    
            mappings[header] = matched_label
            
        return mappings
