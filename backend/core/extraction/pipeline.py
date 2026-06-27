import os
from openai import OpenAI
from backend.core.schema import DocumentBundle, ValidationReport, AuditMetadata
from backend.core.schema.processing import ProcessingContext
from backend.core.extraction.loader import load_document
from backend.core.extraction.ocr import extract_ocr_document, extract_page_text_only
from backend.core.extraction.layout import analyze_layout
from backend.core.extraction.candidate_detector import run_all_detectors
from backend.core.resolver import resolve_all_candidates
from backend.core.extraction.extractor import run_ai_extraction
from backend.core.mappers.gemini_mapper import map_gemini_to_canonical
from backend.core.extraction.session import ExtractionSession

def process_document(document_path: str, context: ProcessingContext) -> DocumentBundle:
    """
    Orchestrates the modular document intelligence pipeline:
    Loader -> OCR -> Layout -> Candidate Detection -> Resolver -> AI Extractor -> Mapper.
    """
    # 1. Loader
    document = load_document(document_path, upload_metadata={"run_id": context.run_id, "firm_id": context.firm_id})
    
    # 2. OCR Engine
    ocr_doc = extract_ocr_document(document_path)
    document.pages = extract_page_text_only(document_path)
    
    # 3. Layout Analysis
    layout_analysis = analyze_layout(ocr_doc)
    
    # 4. Candidate Detection
    candidates = run_all_detectors(ocr_doc)
    
    # 5. Field Resolver
    resolved = resolve_all_candidates(candidates)
    
    # Resolve client credentials based on context provider
    if context.provider == "openrouter":
        base_url = "https://openrouter.ai/api/v1"
        api_key = os.getenv("OPENROUTER_API_KEY", "dummy")
    elif context.provider == "groq":
        base_url = "https://api.groq.com/openai/v1"
        api_key = os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY")
    elif context.provider == "gemini":
        base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
        api_key = os.getenv("GEMINI_API_KEY", "")
    elif context.provider == "ollama":
        base_url = os.getenv("OLLAMA_API_BASE", "http://localhost:11434/v1")
        api_key = os.getenv("OLLAMA_API_KEY", "ollama")
    else: # Default gemini open-ai native proxy wrapper
        if os.getenv("GROQ_API_KEY"):
            base_url = "https://api.groq.com/openai/v1"
            api_key = os.getenv("GROQ_API_KEY")
        else:
            base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
            api_key = os.getenv("GEMINI_API_KEY", "")

    client = OpenAI(api_key=api_key, base_url=base_url)
    
    # 6. AI Extraction
    invoice_type = context.configuration.get("invoice_type", "both")
    raw_extracted = run_ai_extraction(
        layout_analysis, 
        candidates, 
        client, 
        context.model, 
        invoice_type=invoice_type
    )
    
    # 7. Canonical Mapping
    canonical_invoice = map_gemini_to_canonical(raw_extracted)
    
    # Run Financial Reconciliation
    from backend.core.reconciliation import FinancialReconciliationEngine
    reconciler = FinancialReconciliationEngine()
    recon_report = reconciler.reconcile(canonical_invoice)
    
    # Run CA Compliance Validation
    from backend.core.validation import ValidationEngine
    val_engine = ValidationEngine()
    val_report = val_engine.validate(canonical_invoice)
    
    # 8. Store session state
    session = ExtractionSession(
        document=document,
        context=context,
        ocr=ocr_doc,
        layout=layout_analysis.regions,
        candidates=candidates,
        resolved_fields=resolved,
        llm_outputs={"raw_extracted": raw_extracted},
        canonical=canonical_invoice,
        validation=val_report
    )
    
    # 9. Assemble and return bundle
    audit = AuditMetadata(
        extraction_id=context.run_id,
        model_identifier=context.model,
        prompt_version=context.prompt_version,
        pipeline_version=context.pipeline_version
    )
    
    bundle = DocumentBundle(
        document=document,
        invoice=canonical_invoice,
        validation=val_report,
        audit=audit
    )
    
    # Cache raw extracted in bundle for backward compatibility mapping
    bundle.__dict__["_raw_extracted"] = raw_extracted
    bundle.__dict__["reconciliation"] = recon_report
    
    return bundle
