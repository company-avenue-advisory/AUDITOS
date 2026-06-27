import hashlib
import os
import uuid
from typing import Optional, Dict, Any
import fitz # PyMuPDF
from backend.core.schema import Document, DocumentMetadata

def compute_checksum(file_path: str) -> str:
    """
    Computes the SHA-256 checksum of a file.
    """
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    return sha256.hexdigest()

def load_document(file_path: str, upload_metadata: Optional[Dict[str, Any]] = None) -> Document:
    """
    Loads a PDF file and constructs the base Document object containing metadata.
    Does NOT perform OCR or extraction.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    filename = os.path.basename(file_path)
    checksum = compute_checksum(file_path)
    
    # Open with fitz to count pages
    doc = fitz.open(file_path)
    page_count = len(doc)
    doc.close()
    
    # Guess mime type based on extension
    ext = os.path.splitext(file_path)[1].lower()
    mime_type = "application/pdf" if ext == ".pdf" else "image/png"
    
    metadata = DocumentMetadata(
        filename=filename,
        checksum=checksum,
        upload_metadata=upload_metadata or {},
        storage_location=os.path.abspath(file_path),
        page_count=page_count,
        mime_type=mime_type,
        ocr_engine=None,
        language="en"
    )
    
    return Document(
        document_id=str(uuid.uuid4()),
        metadata=metadata,
        pages=[]
    )
