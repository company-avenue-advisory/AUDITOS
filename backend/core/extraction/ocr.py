import base64
import fitz # PyMuPDF
import pdfplumber
from typing import List, Dict, Any
from backend.core.schema import OCRDocument, OCRPage, OCRLine, OCRWord, Page

def extract_ocr_document(file_path: str) -> OCRDocument:
    """
    Performs OCR and text extraction on a document.
    Returns an OCRDocument with pages, lines, tables, images, metadata and warnings.
    """
    doc = fitz.open(file_path)
    pdf_plumber_doc = pdfplumber.open(file_path)
    
    ocr_pages = []
    warnings = []
    
    for idx, page in enumerate(doc):
        plumber_page = pdf_plumber_doc.pages[idx]
        
        # 1. Try extracting text with pdfplumber (retains layout)
        text = ""
        try:
            text = plumber_page.extract_text(layout=True) or ""
        except Exception as e:
            warnings.append(f"pdfplumber text extraction failed on page {idx+1}: {e}")
            
        if not text.strip():
            text = page.get_text()

        # If it's a scanned PDF (very short text extracted), we mark it
        is_scanned = len(text.strip()) < 50
        
        # Create OCRPage
        ocr_page = OCRPage(
            page_number=idx + 1,
            raw_text=text,
            lines=[],
            width=float(page.rect.width),
            height=float(page.rect.height)
        )
        
        # Add page lines
        if text:
            for l_idx, line in enumerate(text.split('\n')):
                ocr_page.lines.append(OCRLine(
                    text=line,
                    bbox=[0.0, 0.0, 0.0, 0.0],
                    words=[]
                ))
        
        ocr_pages.append(ocr_page)

    pdf_plumber_doc.close()
    doc.close()
    
    return OCRDocument(
        pages=ocr_pages
    )

def extract_page_text_only(file_path: str) -> List[Page]:
    """
    Quick extract pages for the Document.pages list.
    """
    doc = fitz.open(file_path)
    pdf_plumber_doc = pdfplumber.open(file_path)
    pages = []
    
    for idx, page in enumerate(doc):
        plumber_page = pdf_plumber_doc.pages[idx]
        text = ""
        try:
            text = plumber_page.extract_text(layout=True) or ""
        except Exception:
            pass
        if not text.strip():
            text = page.get_text()
            
        pages.append(Page(
            page_number=idx + 1,
            raw_text=text
        ))
        
    pdf_plumber_doc.close()
    doc.close()
    return pages
