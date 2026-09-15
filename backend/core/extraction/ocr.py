from typing import List
from docling.document_converter import DocumentConverter
from backend.core.schema import OCRDocument, OCRPage, OCRLine, Page

# Loads Docling's layout models once per worker process (not per document).
_converter = DocumentConverter()


def extract_ocr_document(file_path: str) -> OCRDocument:
    """
    Parses a document with Docling and returns one page per OCRPage, with
    layout-preserving Markdown (tables rendered as Markdown tables) in
    raw_text instead of pdfplumber's whitespace-flattened text.

    This is the single Docling conversion for the document — pages_from_ocr_document()
    reuses this result rather than re-parsing.
    """
    doc = _converter.convert(file_path).document

    ocr_pages = []
    for page_no in range(1, doc.num_pages() + 1):
        text = doc.export_to_markdown(page_no=page_no) or ""
        page_item = doc.pages.get(page_no)
        size = page_item.size if page_item else None

        ocr_page = OCRPage(
            page_number=page_no,
            raw_text=text,
            lines=[
                OCRLine(text=line, bbox=[0.0, 0.0, 0.0, 0.0], words=[])
                for line in text.split("\n")
            ] if text else [],
            width=float(size.width) if size else 0.0,
            height=float(size.height) if size else 0.0,
        )
        ocr_pages.append(ocr_page)

    return OCRDocument(pages=ocr_pages)


def pages_from_ocr_document(ocr_document: OCRDocument) -> List[Page]:
    """
    Derives the Document.pages list from an already-parsed OCRDocument, so the
    PDF is parsed by Docling exactly once per document.
    """
    return [
        Page(page_number=p.page_number, raw_text=p.raw_text)
        for p in ocr_document.pages
    ]
