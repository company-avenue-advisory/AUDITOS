import fitz  # PyMuPDF
import re
from typing import Dict, Any
from pydantic import BaseModel, Field

class UdyamCertificateInfo(BaseModel):
    udyam_number: str = Field(..., description="Udyam Registration Number")
    enterprise_name: str = Field(..., description="Name of the Enterprise")
    major_activity: str = Field(..., description="Major Activity (Manufacturing or Services)")
    enterprise_type: str = Field(..., description="Enterprise Type (MICRO, SMALL, MEDIUM, or LARGE)")

def parse_udyam_certificate(pdf_bytes: bytes) -> Dict[str, Any]:
    """
    Parses an uploaded Udyam Registration Certificate PDF.
    Extracts registration number, name, major activity, and category.
    """
    # Open the PDF from memory
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    text = ""
    for page in doc:
        text += page.get_text() + "\n"
        
    doc.close()
    
    print("--- EXTRACTED PDF TEXT ---")
    print(text[:2000]) # print first 2000 chars to logs for debugging
    print("--------------------------")

    # 1. Extract Udyam Number
    # Format: UDYAM-XX-00-0000000 (e.g. UDYAM-MH-12-0089123)
    udyam_pattern = r"\b(UDYAM-[A-Z]{2}-\d{2}-\d{7})\b"
    udyam_match = re.search(udyam_pattern, text, re.IGNORECASE)
    udyam_number = udyam_match.group(1).upper() if udyam_match else "UNKNOWN"

    # 2. Extract Enterprise Name
    # Look for "Name of Enterprise" or "Name of Unit" followed by colon or newline and value
    name_patterns = [
        r"Name of Enterprise\s*:\s*([^\n]+)",
        r"Name of the Enterprise\s*:\s*([^\n]+)",
        r"NAME OF ENTERPRISE\s+([^\n]+)",
        r"M/s\s*:\s*([^\n]+)",
        r"M/S\s+([^\n]+)",
    ]
    enterprise_name = "UNKNOWN VENDOR"
    for pattern in name_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            # Clean up name: strip whitespace and common prefix spaces
            enterprise_name = match.group(1).strip()
            # If name matches a table border or multiple values, strip extra
            enterprise_name = re.split(r"[:\t\r]", enterprise_name)[0].strip()
            break
            
    # Fallback name extraction if UNKNOWN: look for text around "M/S" without colon
    if enterprise_name == "UNKNOWN VENDOR":
        ms_match = re.search(r"M/S\s+([A-Z0-9\s,&.\(\)]+)", text, re.IGNORECASE)
        if ms_match:
            enterprise_name = ms_match.group(1).strip()

    # 3. Extract Major Activity
    # Usually "Manufacturing" or "Services"
    activity_match = re.search(r"\b(manufacturing|services)\b", text, re.IGNORECASE)
    major_activity = activity_match.group(1).capitalize() if activity_match else "Services"

    # 4. Extract Enterprise Classification (MICRO, SMALL, MEDIUM)
    # Search for "Enterprise Type" or "Classification" and find the classification category.
    # We can also do a broad search since Udyam certificates will list the current category.
    # Micro/Small/Medium is often explicitly listed next to "Enterprise Type" or "Category"
    type_match = re.search(r"\b(micro|small|medium|large)\b", text, re.IGNORECASE)
    
    # Let's search in proximity to "Enterprise Type" first
    enterprise_type = "UNKNOWN"
    type_block_match = re.search(r"(?:Enterprise Type|Classification|Category)[\s\S]{0,100}\b(micro|small|medium|large)\b", text, re.IGNORECASE)
    if type_block_match:
        enterprise_type = type_block_match.group(1).upper()
    elif type_match:
        enterprise_type = type_match.group(1).upper()
        
    return {
        "udyam_number": udyam_number,
        "enterprise_name": enterprise_name,
        "major_activity": major_activity,
        "enterprise_type": enterprise_type
    }
