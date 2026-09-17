# Renders a scanned/photographed PDF's pages to images and runs each
# through vision_extractor.extract_from_image, so genuine scans get direct
# multimodal extraction instead of docling's OCR-then-text pipeline (which
# was both the production droplet's memory problem and, per
# vision_extractor.py's own history, a source of wrong supplier names and
# missed GSTINs on garbled OCR passes).

import os
import tempfile
import fitz  # PyMuPDF
from vision_extractor import extract_from_image


def render_pdf_pages_to_images(pdf_path: str, dpi: int = 200) -> list:
    """
    Renders each page of a PDF to a temp JPEG file. Caller is responsible
    for deleting the returned paths (see extract_scan_via_vision).
    """
    doc = fitz.open(pdf_path)
    paths = []
    try:
        for page in doc:
            pix = page.get_pixmap(dpi=dpi)
            fd, path = tempfile.mkstemp(suffix=".jpg")
            os.close(fd)
            pix.save(path)
            paths.append(path)
    finally:
        doc.close()
    return paths


def extract_scan_via_vision(pdf_path: str, buyer_name: str, buyer_gstin: str) -> list:
    """
    Renders every page of a scanned PDF to an image and runs vision
    extraction on each, returning a flat list of invoice dicts (in
    vision_extractor's own schema — see VISION_SCHEMA) across all pages.
    A single page can itself yield multiple invoices (e.g. two receipts
    photographed together), which vision_extractor already handles.
    """
    image_paths = render_pdf_pages_to_images(pdf_path)
    all_invoices = []
    try:
        for img_path in image_paths:
            all_invoices.extend(extract_from_image(img_path, buyer_name, buyer_gstin))
    finally:
        for p in image_paths:
            try:
                os.remove(p)
            except OSError:
                pass
    return all_invoices
