from typing import List, Optional
import fitz  # PyMuPDF
from backend.core.schema import OCRDocument, OCRPage, OCRLine, Page

# Docling pulls in torch + its layout/table/easyocr models, which is both
# slow to import and heavy in RAM. Import and instantiate it lazily on first
# actual scan, so a worker that only ever sees digitally-generated invoices
# (the common case) never pays that cost at all.
_converter = None


def _get_converter():
    global _converter
    if _converter is None:
        from docling.document_converter import DocumentConverter
        _converter = DocumentConverter()
    return _converter

# Most invoices are digitally generated (Tally/Zoho/ERP exports) and already
# carry a real text layer that pymupdf reads for free, no ML models. Only
# genuine scans/photographs need docling's layout+table+easyocr pipeline,
# which is what OOMs the small production droplet. Thresholds: a page with
# a real text layer typically has hundreds of non-whitespace chars, so 40/page
# comfortably covers even a short one-line receipt while still rejecting a
# near-empty scanned page; the 50% ratio catches a text layer that's mostly
# layout whitespace/garbage rather than actual content.
_MIN_CHARS_PER_PAGE = 40
_MIN_NON_WHITESPACE_RATIO = 0.5


def _has_usable_text_layer(pages_text: List[str]) -> bool:
    if not pages_text:
        return False
    raw_chars = sum(len(t) for t in pages_text)
    non_ws_chars = sum(len("".join(t.split())) for t in pages_text)
    if non_ws_chars / len(pages_text) < _MIN_CHARS_PER_PAGE:
        return False
    if raw_chars and non_ws_chars / raw_chars < _MIN_NON_WHITESPACE_RATIO:
        return False
    return True


def needs_heavy_ocr(file_path: str) -> bool:
    """
    Cheap lane check (pymupdf only, no docling) for callers that must decide
    which concurrency lane/queue a file belongs to *before* running the full
    extraction — e.g. async_tasks.py picking the fast-lane vs heavy-lane
    semaphore. Returns True only for genuine scans/photographs.
    """
    try:
        doc = fitz.open(file_path)
    except Exception:
        return True  # unreadable by pymupdf — let docling have a try

    try:
        pages_text = [page.get_text() for page in doc]
        return not _has_usable_text_layer(pages_text)
    finally:
        doc.close()


def _text_layer_from_pymupdf(file_path: str) -> Optional[OCRDocument]:
    """
    Fast path: reads each page's existing text layer via pymupdf. Returns
    None when the PDF has no usable text layer (a scan/photo), so the
    caller falls back to docling's OCR pipeline.
    """
    try:
        doc = fitz.open(file_path)
    except Exception:
        return None

    try:
        pages_text = [page.get_text() for page in doc]
        if not _has_usable_text_layer(pages_text):
            return None

        ocr_pages = []
        for page_no, text in enumerate(pages_text, start=1):
            rect = doc[page_no - 1].rect
            ocr_pages.append(OCRPage(
                page_number=page_no,
                raw_text=text,
                lines=[
                    OCRLine(text=line, bbox=[0.0, 0.0, 0.0, 0.0], words=[])
                    for line in text.split("\n")
                ] if text else [],
                width=float(rect.width),
                height=float(rect.height),
            ))
        return OCRDocument(pages=ocr_pages)
    finally:
        doc.close()


def extract_ocr_document(file_path: str) -> OCRDocument:
    """
    Returns one OCRPage per page. Tries pymupdf's native text layer first
    (near-zero memory, no ML); falls back to Docling's full OCR pipeline
    (layout transformer + tableformer + easyocr) only for scans/photographs
    that have no usable embedded text.

    This is the single parse for the document — pages_from_ocr_document()
    reuses this result rather than re-parsing.
    """
    fast_result = _text_layer_from_pymupdf(file_path)
    if fast_result is not None:
        return fast_result

    doc = _get_converter().convert(file_path).document

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
