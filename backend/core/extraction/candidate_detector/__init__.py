from typing import List
from .candidate import Candidate
from .gst_candidates import detect_gst_candidates
from .invoice_candidates import detect_invoice_number_candidates
from .tax_candidates import detect_tax_candidates
from .totals_candidates import detect_totals_candidates
from .metadata_candidates import detect_metadata_candidates

def run_all_detectors(ocr_document) -> List[Candidate]:
    """
    Orchestrates all deterministic detectors, scanning the OCRDocument to extract candidates.
    """
    candidates = []
    candidates.extend(detect_gst_candidates(ocr_document))
    candidates.extend(detect_invoice_number_candidates(ocr_document))
    candidates.extend(detect_tax_candidates(ocr_document))
    candidates.extend(detect_totals_candidates(ocr_document))
    candidates.extend(detect_metadata_candidates(ocr_document))
    return candidates
