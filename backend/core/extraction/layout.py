import re
from typing import Dict, Any, List
from backend.core.schema import OCRDocument

class LayoutAnalysis:
    """
    Groups OCR document lines into logical, semantic regions.
    """
    def __init__(self, regions: Dict[str, str]):
        self.regions = regions

    def get_region_text(self, region_name: str) -> str:
        return self.regions.get(region_name, "")

def analyze_layout(ocr_document: OCRDocument) -> LayoutAnalysis:
    """
    Analyzes spatial and keyword configurations of the OCR document to separate 
    it into semantic blocks (Header/Metadata, Items Table, Totals/Tax summary).
    """
    regions = {
        "metadata_region": "",
        "items_table_region": "",
        "totals_region": "",
        "payment_region": "",
        "footer_region": ""
    }
    
    # Simple rule-based lines partitioner
    metadata_lines = []
    items_lines = []
    totals_lines = []
    payment_lines = []
    footer_lines = []
    
    table_started = False
    totals_started = False
    
    table_headers = ["particulars", "description", "hsn", "qty", "quantity", "rate", "taxable"]
    totals_keywords = [
        "subtotal", "cgst", "sgst", "igst", "cess", "round off", 
        "grand total", "net amount", "total amount", "total taxable", 
        "total invoice", "total tax", "final total"
    ]
    payment_keywords = ["bank name", "account no", "a/c", "ifsc", "rtgs", "neft"]
    
    for page in ocr_document.pages:
        lines = page.raw_text.split('\n')
        for line in lines:
            lower_line = line.lower()
            
            # Check for region transitions
            if any(h in lower_line for h in table_headers) and not table_started:
                table_started = True
                
            if any(t in lower_line for t in totals_keywords) and table_started:
                totals_started = True
                
            # Classify lines
            if any(p in lower_line for p in payment_keywords):
                payment_lines.append(line)
            elif totals_started:
                totals_lines.append(line)
            elif table_started:
                items_lines.append(line)
            else:
                metadata_lines.append(line)
                
    regions["metadata_region"] = "\n".join(metadata_lines)
    regions["items_table_region"] = "\n".join(items_lines)
    regions["totals_region"] = "\n".join(totals_lines)
    regions["payment_region"] = "\n".join(payment_lines)
    regions["footer_region"] = "\n".join(footer_lines)
    
    return LayoutAnalysis(regions)
