from typing import Optional, Any, Dict, List
from pydantic import BaseModel, Field
from backend.core.schema import Document, OCRDocument, CanonicalInvoice, ValidationReport, DocumentBundle
from backend.core.schema.processing import ProcessingContext
from backend.core.extraction.candidate_detector import Candidate

class ExtractionSession(BaseModel):
    """
    State container tracing all stages of document analysis and LLM extractions.
    """
    document: Document
    context: ProcessingContext
    ocr: Optional[OCRDocument] = None
    layout: Optional[Dict[str, Any]] = None
    candidates: List[Candidate] = Field(default_factory=list)
    resolved_fields: Dict[str, Any] = Field(default_factory=dict)
    llm_outputs: Dict[str, Any] = Field(default_factory=dict)
    canonical: Optional[CanonicalInvoice] = None
    validation: Optional[ValidationReport] = None
    metrics: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        arbitrary_types_allowed = True
