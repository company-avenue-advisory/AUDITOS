from typing import Optional, List, Dict, Any
from pydantic import Field, BaseModel
from .bundle import VersionedBaseModel

class PageMetadata(BaseModel):
    """
    Metadata relating to visual layout and characteristics of a page.
    """
    width: Optional[float] = Field(None, description="Page width in pixels/points")
    height: Optional[float] = Field(None, description="Page height in pixels/points")
    dpi: Optional[int] = Field(None, description="DPI of the rendered image or scan")

class Page(VersionedBaseModel):
    """
    Represents a single page within the document, storing layout, text and visual properties.
    """
    page_number: int = Field(..., description="1-indexed page number in the source file")
    raw_text: str = Field("", description="Extracted raw text from this page")
    rotation: float = Field(0.0, description="Page rotation in degrees (e.g. 0, 90, 180, 270)")
    layout_metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata from layout extraction models")
    ocr_metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata from the OCR engine")
    bounding_boxes: List[Dict[str, Any]] = Field(default_factory=list, description="Coordinates and tokens for visual search/highlighting")

class DocumentMetadata(BaseModel):
    """
    Technical and intake metadata for the uploaded file.
    """
    filename: str = Field(..., description="Original name of the uploaded file")
    checksum: Optional[str] = Field(None, description="SHA-256 hash checksum of the file content")
    upload_metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata captured during upload")
    storage_location: Optional[str] = Field(None, description="GCS/S3 URI or local path where the raw file is stored")
    page_count: int = Field(0, description="Total number of pages in the document")
    mime_type: Optional[str] = Field(None, description="Mime type of the file (e.g. application/pdf, image/png)")
    ocr_engine: Optional[str] = Field(None, description="Name/version of the OCR engine used")
    language: Optional[str] = Field(None, description="Primary detected language of the document")
    processing_metadata: Dict[str, Any] = Field(default_factory=dict, description="Auxiliary key-value details from pipeline steps")

class Document(VersionedBaseModel):
    """
    Root Document model containing files, metadata, and visual structure.
    """
    document_id: str = Field(..., description="UUID or unique identifier generated for this document")
    metadata: DocumentMetadata = Field(..., description="Technical file metadata")
    pages: List[Page] = Field(default_factory=list, description="List of pages and their visual contents")

class OCRWord(BaseModel):
    text: str
    confidence: float
    bbox: List[float]  # [x_min, y_min, x_max, y_max]

class OCRLine(BaseModel):
    text: str
    bbox: List[float]
    words: List[OCRWord] = Field(default_factory=list)

class OCRPage(BaseModel):
    page_number: int
    raw_text: str = ""
    lines: List[OCRLine] = Field(default_factory=list)
    width: float
    height: float

class OCRDocument(VersionedBaseModel):
    """
    Deep OCR results detailing visual word coordinate boxes for accurate UI highlighting.
    """
    pages: List[OCRPage] = Field(default_factory=list)
