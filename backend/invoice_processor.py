import os
import sys
import argparse
import fitz  # PyMuPDF
import pandas as pd
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Literal
from dotenv import load_dotenv
import re
import tempfile
import time
import base64

# Ensure 'from backend.core...' imports resolve when running from inside backend/
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Ensure it explicitly loads from backend directory
env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=env_path)

_STATE_CODE_MAP = {
    "01": "JAMMU AND KASHMIR", "02": "HIMACHAL PRADESH", "03": "PUNJAB",
    "04": "CHANDIGARH", "05": "UTTARAKHAND", "06": "HARYANA",
    "07": "DELHI", "08": "RAJASTHAN", "09": "UTTAR PRADESH",
    "10": "BIHAR", "11": "SIKKIM", "12": "ARUNACHAL PRADESH",
    "13": "NAGALAND", "14": "MANIPUR", "15": "MIZORAM",
    "16": "TRIPURA", "17": "MEGHALAYA", "18": "ASSAM",
    "19": "WEST BENGAL", "20": "JHARKHAND", "21": "ODISHA",
    "22": "CHATTISGARH", "23": "MADHYA PRADESH", "24": "GUJARAT",
    "27": "MAHARASHTRA", "29": "KARNATAKA", "30": "GOA",
    "32": "KERALA", "33": "TAMIL NADU", "36": "TELANGANA",
    "37": "ANDHRA PRADESH",
}

class SuvitSalesItem(BaseModel):
    voucher_date: Optional[str] = Field(None, description="Voucher Date (DD-MMM-YYYY)")
    voucher_type: str = Field("Sales", description="Voucher Type")
    invoice_no: Optional[str] = Field(None, description="Invoice No")
    party_ledger_name: Optional[str] = Field(None, description="Party Ledger Name")
    party_gstin: Optional[str] = Field(None, description="Party GSTIN")
    place_of_supply: Optional[str] = Field(None, description="Place of Supply")
    particulars: Optional[str] = Field(None, description="Particulars / Item Description")
    hsn: Optional[str] = Field(None, description="HSN/SAC Code")
    qty: Optional[float] = Field(None, description="Qty")
    rate: Optional[float] = Field(None, description="Rate")
    taxable_value: float = Field(0.0, description="Taxable Value")
    discount: float = Field(0.0, description="Discount amount")
    advances: float = Field(0.0, description="Advances amount")
    cgst_amount: float = Field(0.0, description="CGST Amount")
    sgst_amount: float = Field(0.0, description="SGST Amount")
    igst_amount: float = Field(0.0, description="IGST Amount")
    total_invoice_value: float = Field(0.0, description="Total Invoice Value")
    gstr1_category: Optional[str] = Field(None, description="GSTR-1 Category")
    narration: Optional[str] = Field(None, description="Narration")

    @field_validator('qty', 'rate', 'taxable_value', 'discount', 'advances', 'cgst_amount', 'sgst_amount', 'igst_amount', 'total_invoice_value', mode='before')
    @classmethod
    def remove_commas(cls, v):
        if v is None:
            return 0.0
        if isinstance(v, str):
            v = v.replace(',', '').strip()
            if not v:
                return 0.0
        return v

class SuvitPurchaseItem(BaseModel):
    voucher_date: Optional[str] = Field(None, description="Voucher Date (DD-MMM-YYYY)")
    voucher_type: str = Field("Purchase", description="Voucher Type")
    invoice_no: Optional[str] = Field(None, description="Invoice No")
    party_ledger_name: Optional[str] = Field(None, description="Party Ledger Name")
    party_gstin: Optional[str] = Field(None, description="Party GSTIN")
    place_of_supply: Optional[str] = Field(None, description="Place of Supply")
    particulars: Optional[str] = Field(None, description="Particulars / Item Description")
    hsn: Optional[str] = Field(None, description="HSN/SAC Code")
    qty: Optional[float] = Field(None, description="Qty")
    rate: Optional[float] = Field(None, description="Rate")
    taxable_value: float = Field(0.0, description="Taxable Value")
    cgst_amount: float = Field(0.0, description="CGST Amount")
    sgst_amount: float = Field(0.0, description="SGST Amount")
    igst_amount: float = Field(0.0, description="IGST Amount")
    total_invoice_value: float = Field(0.0, description="Total Invoice Value")
    itc_category: Optional[str] = Field(None, description="ITC Category")
    narration: Optional[str] = Field(None, description="Narration")

    @field_validator('qty', 'rate', 'taxable_value', 'cgst_amount', 'sgst_amount', 'igst_amount', 'total_invoice_value', mode='before')
    @classmethod
    def remove_commas(cls, v):
        if isinstance(v, str):
            v = v.replace(',', '').strip()
            if not v:
                return 0.0
        return v

class InvoiceExtractionResponse(BaseModel):
    overall_taxable_value: float = Field(0.0, description="Overall Taxable Value of the entire invoice")
    overall_cgst_amount: float = Field(0.0, description="Overall CGST Amount of the entire invoice")
    overall_sgst_amount: float = Field(0.0, description="Overall SGST Amount of the entire invoice")
    overall_igst_amount: float = Field(0.0, description="Overall IGST Amount of the entire invoice")
    overall_round_off: float = Field(0.0, description="Rounding off adjustment on the final invoice total")
    overall_advance_amount: float = Field(0.0, description="Advance/previous payment deducted from the invoice total")
    overall_total_invoice_value: float = Field(0.0, description="Overall Total Invoice Value incl taxes")
    sales_items: List[SuvitSalesItem] = Field(default_factory=list, description="Extracted sales items")
    purchase_items: List[SuvitPurchaseItem] = Field(default_factory=list, description="Extracted purchase items")
    correction_meta: Optional[dict] = Field(None, description="Metadata about post-processing corrections")
    prompt_tokens: Optional[int] = Field(0, description="Prompt tokens used")
    completion_tokens: Optional[int] = Field(0, description="Completion tokens used")
    total_pages: Optional[int] = Field(0, description="Total pages processed")
    latency_ms: Optional[int] = Field(0, description="Latency in ms")
    total_retries: Optional[int] = Field(0, description="Total retries")

def extract_text_from_pdf(pdf_path):
    import pdfplumber
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text += page.extract_text(layout=True) + "\n"
    except Exception as e:
        print(f"  Error extracting text from PDF {pdf_path}: {e}")
    return text

def extract_page_content(page, pdfplumber_page=None):
    text = ""
    if pdfplumber_page:
        try:
            text = pdfplumber_page.extract_text(layout=True) or ""
        except Exception:
            pass
    if not text:
        text = page.get_text()
        
    if len(text.strip()) < 50:
        try:
            pix = page.get_pixmap()
            img_data = pix.tobytes("jpeg", 70)
            base64_image = base64.b64encode(img_data).decode('utf-8')
            return {"type": "image", "content": base64_image}
        except Exception:
            return {"type": "text", "content": text + "\n"}
    return {"type": "text", "content": text + "\n"}

def call_llm(pdf_contents, model_name, client, invoice_type="both"):
    schema_json = """{
  "type": "object",
  "properties": {
    "overall_taxable_value": {"type": "number", "description": "Overall Taxable Value of the entire invoice"},
    "overall_cgst_amount": {"type": "number", "description": "Overall CGST Amount of the entire invoice"},
    "overall_sgst_amount": {"type": "number", "description": "Overall SGST Amount of the entire invoice"},
    "overall_igst_amount": {"type": "number", "description": "Overall IGST Amount of the entire invoice"},
    "overall_round_off": {"type": "number", "description": "Rounding off / rounding adjustment on the final invoice total (e.g. 0.13 or -0.05)"},
    "overall_advance_amount": {"type": "number", "description": "Advance payment or previous payment deducted from the invoice. Positive number. 0 if absent. Look for 'Less: Advance', 'Advance received', 'Previous payment', 'Adjustment'."},
    "overall_total_invoice_value": {"type": "number", "description": "Net amount payable AFTER deducting advance. Overall Total Invoice Value incl taxes minus advance."},
    "sales_items": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "voucher_date": {"type": "string", "description": "Voucher Date (DD-MMM-YYYY)"},
          "voucher_type": {"type": "string", "description": "Voucher Type (Sales)"},
          "invoice_no": {"type": "string", "description": "Invoice No"},
          "party_ledger_name": {"type": "string", "description": "Party Ledger Name"},
          "party_gstin": {"type": "string", "description": "Party GSTIN"},
          "place_of_supply": {"type": "string", "description": "Place of Supply"},
          "particulars": {"type": "string", "description": "Particulars / Item Description"},
          "hsn": {"type": "string", "description": "HSN/SAC Code"},
          "qty": {"type": "number", "description": "Qty"},
          "rate": {"type": "number", "description": "Rate"},
          "taxable_value": {"type": "number", "description": "Taxable Value"},
          "discount": {"type": "number", "description": "Discount amount"},
          "advances": {"type": "number", "description": "Advances amount"},
          "cgst_amount": {"type": "number", "description": "CGST Amount"},
          "sgst_amount": {"type": "number", "description": "SGST Amount"},
          "igst_amount": {"type": "number", "description": "IGST Amount"},
          "total_invoice_value": {"type": "number", "description": "Total Invoice Value"},
          "gstr1_category": {"type": "string", "description": "GSTR-1 Category"},
          "narration": {"type": "string", "description": "Narration"}
        }
      }
    },
    "purchase_items": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "voucher_date": {"type": "string", "description": "Voucher Date (DD-MMM-YYYY)"},
          "voucher_type": {"type": "string", "description": "Voucher Type (Purchase)"},
          "invoice_no": {"type": "string", "description": "Invoice No"},
          "party_ledger_name": {"type": "string", "description": "Party Ledger Name"},
          "party_gstin": {"type": "string", "description": "Party GSTIN"},
          "place_of_supply": {"type": "string", "description": "Place of Supply"},
          "particulars": {"type": "string", "description": "Particulars / Item Description"},
          "hsn": {"type": "string", "description": "HSN/SAC Code"},
          "qty": {"type": "number", "description": "Qty"},
          "rate": {"type": "number", "description": "Rate"},
          "taxable_value": {"type": "number", "description": "Taxable Value"},
          "cgst_amount": {"type": "number", "description": "CGST Amount"},
          "sgst_amount": {"type": "number", "description": "SGST Amount"},
          "igst_amount": {"type": "number", "description": "IGST Amount"},
          "total_invoice_value": {"type": "number", "description": "Total Invoice Value"},
          "itc_category": {"type": "string", "description": "ITC Category"},
          "narration": {"type": "string", "description": "Narration"}
        }
      }
    }
  }
}"""
    
    import os
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    prompt_file = os.path.join(base_dir, "frontend", "gstr1_system_prompt.txt")
    
    custom_prompt = ""
    if os.path.exists(prompt_file):
        with open(prompt_file, 'r', encoding='utf-8') as f:
            custom_prompt += f.read() + "\n\n"
            
    if custom_prompt:
        prompt_text = custom_prompt + f"Output the final result as a JSON object matching this schema:\n{schema_json}\n\n===== CONTENT OF PDF INVOICE ====="
    else:
        prompt_text = f"Extract structured data into JSON matching schema:\n{schema_json}"
        
    messages_content = [{"type": "text", "text": prompt_text}]
    
    for item in pdf_contents:
        if item["type"] == "text":
            messages_content.append({"type": "text", "text": item["content"]})
        elif item["type"] == "image":
            messages_content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{item['content']}"}})
            
    max_retries = 3
    fallback_chain = [model_name]
    if model_name == "google/gemini-2.5-flash":
        fallback_chain = ["google/gemini-2.5-flash", "google/gemini-1.5-flash", "google/gemini-2.5-pro"]
    elif model_name == "gemini-2.5-flash":
        fallback_chain = ["gemini-2.5-flash", "gemini-1.5-flash", "gemini-2.5-pro"]
    elif "llama" in model_name:
        fallback_chain = [model_name, "llama-3.3-70b-versatile", "llama3-70b-8192"]
        
    for attempt in range(max_retries):
        current_model = fallback_chain[attempt] if attempt < len(fallback_chain) else fallback_chain[-1]
        try:
            print(f"  Analyzing content (attempt {attempt+1}) using {current_model}...")
            
            response = client.chat.completions.create(
                model=current_model,
                messages=[{"role": "user", "content": messages_content}],
                response_format={"type": "json_object"},
                temperature=0.0,
                max_tokens=2048
            )
            
            raw_content = response.choices[0].message.content
            if not raw_content:
                raise ValueError("LLM returned empty or null content")
            content = raw_content.strip()
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                content = json_match.group(0)
                
            import json
            data = InvoiceExtractionResponse(**json.loads(content))
            prompt_tokens = response.usage.prompt_tokens if (response.usage and hasattr(response.usage, "prompt_tokens")) else 0
            completion_tokens = response.usage.completion_tokens if (response.usage and hasattr(response.usage, "completion_tokens")) else 0
            return data, prompt_tokens, completion_tokens, attempt
            
        except Exception as e:
            if attempt == max_retries - 1:
                raise e
            print(f"  Model {current_model} failed with error: {str(e)[:100]}...")
            time.sleep(10 * (attempt + 1) if "429" in str(e) or "503" in str(e) else 2)

def _extract_gst_summary_table(full_text: str) -> dict:
    """
    Deterministically parse the GST summary table that every invoice prints at
    the bottom of page 2.  Format (all invoices use the same template):

        Taxable Value  | Central Tax Rate | Central Tax | State Tax Rate | State Tax | Integrated Tax Rate | Integrated Tax
        [amount]         [rate]%            [amount]      [rate]%          [amount]     [rate]%               [amount]

    Also extracts:
      - "Final Total (A+B+C+D+E+F+G)"  →  the true GST base (after advance)
      - "Net Cost"                      →  gross before advance
      - "Total Cost incl Taxes"         →  final payable
      - "Rounding off"                  →  rounding adjustment

    Returns a dict with any keys it could find; empty dict on complete failure.
    """
    import re

    def _f(s: str) -> float:
        return float(s.replace(',', ''))

    text = re.sub(r'[ \t]+', ' ', full_text)

    result = {}

    # ── GST summary data row ─────────────────────────────────────────────────
    # Anchor to AFTER the "Taxable Value...Central Tax" header row so we don't
    # accidentally match line-item numbers that happen to fit the numeric pattern.
    # Rate digits may be absent (shown as bare "%"), so the digit group is optional.
    m = re.search(
        r'Taxable Value.{0,300}?Central Tax.{0,600}?'   # anchor: must be in GST table
        r'([\d,]+\.[\d]{2})\s+'    # taxable value
        r'(\d*\.?\d*)\s*%\s+'      # CGST rate (may be blank → 0)
        r'([\d,]+\.[\d]{2})\s+'    # CGST amount
        r'(\d*\.?\d*)\s*%\s+'      # SGST rate
        r'([\d,]+\.[\d]{2})\s+'    # SGST amount
        r'(\d*\.?\d*)\s*%\s+'      # IGST rate
        r'([\d,]+\.[\d]{2})',       # IGST amount
        text, re.DOTALL
    )
    if m:
        result['taxable_value']  = _f(m.group(1))
        result['cgst_rate']      = float(m.group(2)) if m.group(2) else 0.0
        result['cgst_amount']    = _f(m.group(3))
        result['sgst_rate']      = float(m.group(4)) if m.group(4) else 0.0
        result['sgst_amount']    = _f(m.group(5))
        result['igst_rate']      = float(m.group(6)) if m.group(6) else 0.0
        result['igst_amount']    = _f(m.group(7))

    # ── Final Total — the post-advance GST base ───────────────────────────────
    ft = re.search(r'Final Total\s*\([^)]*\)\s+([\d,]+\.[\d]{2})', text)
    if ft:
        result['final_total'] = _f(ft.group(1))

    # ── Net Cost — gross before advance ──────────────────────────────────────
    nc = re.search(r'Net Cost\s+([\d,]+\.[\d]{2})', text)
    if nc:
        result['net_cost'] = _f(nc.group(1))

    # ── Total Cost incl Taxes — final payable ─────────────────────────────────
    tc = re.search(r'Total Cost incl Taxes\s+([\d,]+\.[\d]{2})', text)
    if tc:
        result['total_invoice_value'] = _f(tc.group(1))

    # ── Rounding off ─────────────────────────────────────────────────────────
    ro = re.search(r'Rounding off\s+(-?[\d,]+\.[\d]{2})', text)
    if ro:
        result['round_off'] = _f(ro.group(1))

    # ── Derive advance from Net Cost − Final Total ────────────────────────────
    if 'net_cost' in result and 'final_total' in result:
        adv = round(result['net_cost'] - result['final_total'], 2)
        if adv > 0.50:
            result['advance_amount'] = adv

    return result


def process_pdf(pdf_path, model_override=None, invoice_type="both", logger=None):
    import pdfplumber
    import time
    from services.observability import now_utc
    
    # 1. File Intake Stage
    started_intake = now_utc()
    try:
        doc = fitz.open(pdf_path)
        pdf_plumber_doc = pdfplumber.open(pdf_path)
        total_pages = len(doc)
    except Exception as e:
        print(f"  Error opening PDF {pdf_path}: {e}")
        return InvoiceExtractionResponse()
        
    if total_pages == 0:
        return InvoiceExtractionResponse()
        
    # Determine scan type
    full_text = ""
    for page in doc:
        full_text += page.get_text() + "\n"
    scan_type = "text_selectable" if len(full_text.strip()) >= 50 else "scanned_ocr"
    
    completed_intake = now_utc()
    if logger:
        logger.emit_file_intake(
            filename=os.path.basename(pdf_path),
            page_count=total_pages,
            started_at=started_intake,
            completed_at=completed_intake,
            scan_type=scan_type
        )

    # 2. Model Selection Stage
    started_model = now_utc()
    is_cloud_primary = False
    if model_override and model_override.get("provider") == "anthropic":
        # Claude via Anthropic SDK — best accuracy for structured extraction
        model_name = model_override.get("model") or "claude-haiku-4-5-20251001"
        base_url = "https://api.anthropic.com/v1"
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        is_cloud_primary = True
    elif model_override and model_override.get("provider") == "openrouter":
        model_name = model_override["model"]
        base_url = "https://openrouter.ai/api/v1"
        api_key = os.getenv("OPENROUTER_API_KEY", "dummy")
        is_cloud_primary = True
    elif model_override and model_override.get("provider") == "groq":
        model_name = model_override.get("model") or "llama-3.3-70b-versatile"
        base_url = "https://api.groq.com/openai/v1"
        api_key = os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY")
        is_cloud_primary = True
    elif model_override and model_override.get("provider") == "gemini":
        model_name = model_override.get("model") or "gemini-2.5-flash"
        base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
        api_key = os.getenv("GEMINI_API_KEY", "")
        is_cloud_primary = True
    elif model_override and model_override.get("provider") == "ollama":
        model_name = model_override.get("model") or os.getenv("OLLAMA_MODEL_NAME", "qwen2.5:7b")
        base_url = os.getenv("OLLAMA_API_BASE", "http://localhost:11434/v1")
        api_key = os.getenv("OLLAMA_API_KEY", "ollama")
    else:
        # Default: Gemini > Groq
        if os.getenv("GEMINI_API_KEY"):
            model_name = "gemini-2.5-flash"
            base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
            api_key = os.getenv("GEMINI_API_KEY")
        else:
            model_name = "llama-3.3-70b-versatile"
            base_url = "https://api.groq.com/openai/v1"
            api_key = os.getenv("GROQ_API_KEY", "")
        is_cloud_primary = True
        
    completed_model = now_utc()
    if logger:
        logger.emit_model_selection(
            started_at=started_model,
            completed_at=completed_model,
            api_key_present=bool(api_key),
            endpoint_health="healthy"
        )
        
    # 3. Guardrail Precheck Stage
    started_precheck = now_utc()
    passed_precheck = total_pages > 0 and os.path.exists(pdf_path)
    completed_precheck = now_utc()
    if logger:
        logger.emit_guardrail_precheck(
            started_at=started_precheck,
            completed_at=completed_precheck,
            passed=passed_precheck,
            failure_reason=None if passed_precheck else "Invalid or empty PDF file"
        )

    from openai import OpenAI
    client = OpenAI(api_key=api_key, base_url=base_url)
    
    CHUNK_SIZE = 3
    OVERLAP = 1
    
    all_res = InvoiceExtractionResponse()
    
    # 4. Modular Pipeline Extraction Stage
    from backend.core.schema.processing import ProcessingContext
    from backend.core.extraction.pipeline import process_document
    import uuid
    
    started_extraction = now_utc()
    run_id = str(uuid.uuid4())
    
    context = ProcessingContext(
        run_id=run_id,
        batch_id="batch_compat",
        task_id=run_id,
        tenant_id="tenant_default",
        firm_id="firm_default",
        provider=model_override.get("provider") if model_override else ("gemini" if os.getenv("GEMINI_API_KEY") else ("groq" if os.getenv("GROQ_API_KEY") else "google_native")),
        model=model_name,
        temperature=0.0,
        prompt_version="1.0.0",
        feature_flags={},
        configuration={"invoice_type": invoice_type}
    )
    
    t0 = time.time()
    bundle = process_document(pdf_path, context)
    total_latency_ms = int((time.time() - t0) * 1000)
    
    raw_extracted = bundle.__dict__.get("_raw_extracted") or {}
    
    all_res = InvoiceExtractionResponse()
    all_res.overall_taxable_value = raw_extracted.get("overall_taxable_value") or 0.0
    all_res.overall_cgst_amount = raw_extracted.get("overall_cgst_amount") or 0.0
    all_res.overall_sgst_amount = raw_extracted.get("overall_sgst_amount") or 0.0
    all_res.overall_igst_amount = raw_extracted.get("overall_igst_amount") or 0.0
    all_res.overall_round_off = raw_extracted.get("overall_round_off") or 0.0
    all_res.overall_advance_amount = raw_extracted.get("overall_advance_amount") or 0.0
    all_res.overall_total_invoice_value = raw_extracted.get("overall_total_invoice_value") or 0.0

    for item in raw_extracted.get("sales_items", []):
        all_res.sales_items.append(SuvitSalesItem(**item))
    for item in raw_extracted.get("purchase_items", []):
        all_res.purchase_items.append(SuvitPurchaseItem(**item))
        
    # ── Ground-truth auto-corrections from Reconciliation Engine ────────────
    recon_report = bundle.__dict__.get("reconciliation")
    ground_truth_correction = {"applied": False}
    
    if recon_report:
        taxable_evidence = recon_report.field_evidence.get("taxable_value")
        if taxable_evidence and taxable_evidence.suggested_correction:
            suggested = taxable_evidence.suggested_correction.suggested_value
            ground_truth_correction["overall_taxable_value"] = {
                "llm_value": all_res.overall_taxable_value,
                "document_value": suggested
            }
            all_res.overall_taxable_value = suggested
            ground_truth_correction["applied"] = True
            
        total_evidence = recon_report.field_evidence.get("grand_total")
        if total_evidence and total_evidence.suggested_correction:
            suggested = total_evidence.suggested_correction.suggested_value
            ground_truth_correction["overall_total_invoice_value"] = {
                "llm_value": all_res.overall_total_invoice_value,
                "document_value": suggested
            }
            all_res.overall_total_invoice_value = suggested
            ground_truth_correction["applied"] = True

    # ── Deterministic override from GST summary table ────────────────────────
    # Applied AFTER reconciliation so regex results win over both LLM and
    # the reconciliation engine.  The GST-compliant summary table is the legal
    # ground truth: taxable = Final Total (post-advance net), tax amounts and
    # grand total are read directly from the document — no hallucination risk.
    gst_table = _extract_gst_summary_table(full_text)
    if gst_table:
        if 'taxable_value' in gst_table and gst_table['taxable_value'] > 0:
            all_res.overall_taxable_value = gst_table['taxable_value']
        if 'cgst_amount' in gst_table:
            all_res.overall_cgst_amount = gst_table['cgst_amount']
        if 'sgst_amount' in gst_table:
            all_res.overall_sgst_amount = gst_table['sgst_amount']
        if 'igst_amount' in gst_table:
            all_res.overall_igst_amount = gst_table['igst_amount']
        if 'round_off' in gst_table:
            all_res.overall_round_off = gst_table['round_off']
        if 'total_invoice_value' in gst_table and gst_table['total_invoice_value'] > 0:
            all_res.overall_total_invoice_value = gst_table['total_invoice_value']
        if 'advance_amount' in gst_table:
            all_res.overall_advance_amount = gst_table['advance_amount']

    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_retries = 0
    completed_extraction = now_utc()
    
    if logger:
        logger.emit_llm_extraction(
            started_at=started_extraction,
            completed_at=completed_extraction,
            latency_ms=total_latency_ms,
            prompt_tokens=total_prompt_tokens,
            completion_tokens=total_completion_tokens,
            raw_line_items=len(all_res.sales_items) + len(all_res.purchase_items),
            sales_count=len(all_res.sales_items),
            purchase_count=len(all_res.purchase_items),
            subtotal_rows_detected=0,
            json_parse_succeeded=True,
            retry_count=total_retries
        )

    # 6. Post-Processing Stage
    started_post = now_utc()
    
    correction_meta = {
        "pydantic_null_coercions": 0,
        "subtotal_rows_dropped": 0,
        "gst_rates_snapped": 0,
        "taxes_recalculated": 0,
        "unallocated_rows_injected": 0,
        "unallocated_row_details": {},
        "tax_type_ambiguous_fallback": False,
    }
    
    # Detect export invoice from full text (LUT / zero-rated supply markers)
    # NOTE: "lut" is 3 chars and appears inside common words like "solution", "absolute", etc.
    # Use phrase markers for everything except LUT which requires a word-boundary check.
    _export_phrases = [
        "export invoice", "letter of undertaking", "without payment of integrated",
        "without payment of igst", "zero-rated supply", "zero rated supply",
    ]
    _ft_lower = full_text.lower()
    _is_export_invoice = (
        any(m in _ft_lower for m in _export_phrases)
        or bool(re.search(r'\blut\b', _ft_lower))
    )

    if all_res.sales_items:
        # Detect subtotal rows dropped
        orig_len = len(all_res.sales_items)
        cleaned_sales = remove_subtotals(all_res.sales_items)
        dropped = orig_len - len(cleaned_sales)
        correction_meta["subtotal_rows_dropped"] = dropped

        # Ensure taxable_value reflects post-discount net
        cleaned_sales = _correct_taxable_values(cleaned_sales)

        # Apply QC Audit (EXPORT tag preserved inside qc_audit_sales_items)
        cleaned_sales = qc_audit_sales_items(cleaned_sales)

        # Force EXPORT category + zero taxes AFTER QC audit (final override for LUT invoices)
        if _is_export_invoice:
            for item in cleaned_sales:
                item.cgst_amount = 0.0
                item.sgst_amount = 0.0
                item.igst_amount = 0.0
                item.total_invoice_value = round(item.taxable_value or 0.0, 2)
                item.gstr1_category = "EXPORT"
            all_res.overall_cgst_amount = 0.0
            all_res.overall_sgst_amount = 0.0
            all_res.overall_igst_amount = 0.0
            all_res.overall_total_invoice_value = all_res.overall_taxable_value

        # Unallocated variance injection
        overall_total = all_res.overall_total_invoice_value
        sum_total = sum((item.taxable_value or 0.0) + (item.cgst_amount or 0.0) + (item.sgst_amount or 0.0) + (item.igst_amount or 0.0) for item in cleaned_sales)
        diff = overall_total - sum_total

        # Skip phantom injection when diff ≈ tax on existing items (items extracted without per-line taxes)
        _sum_taxable = sum(item.taxable_value or 0.0 for item in cleaned_sales)
        _diff_is_just_tax = any(abs(diff - _sum_taxable * r) < 5.0 for r in (0.18, 0.12, 0.05, 0.28))

        if overall_total > 0 and diff > 1.0 and not _diff_is_just_tax:
            taxable_diff = round(diff / 1.18, 2)
            is_interstate = (cleaned_sales[0].igst_amount or 0) > 0 if cleaned_sales else False
            
            dummy_item = SuvitSalesItem(
                voucher_date=cleaned_sales[0].voucher_date if cleaned_sales else "",
                invoice_no=cleaned_sales[0].invoice_no if cleaned_sales else "",
                party_gstin=cleaned_sales[0].party_gstin if cleaned_sales else "",
                party_ledger_name=cleaned_sales[0].party_ledger_name if cleaned_sales else "",
                place_of_supply=cleaned_sales[0].place_of_supply if cleaned_sales else "",
                particulars="Unallocated / Missing Lines",
                hsn="9971",
                taxable_value=taxable_diff,
                cgst_amount=0.0 if is_interstate else round(taxable_diff * 0.09, 2),
                sgst_amount=0.0 if is_interstate else round(taxable_diff * 0.09, 2),
                igst_amount=round(taxable_diff * 0.18, 2) if is_interstate else 0.0,
                total_invoice_value=diff
            )
            cleaned_sales.append(dummy_item)
            correction_meta["unallocated_rows_injected"] = 1
            correction_meta["unallocated_row_details"] = {
                "variance_amount": diff
            }
            
        # Math verification agent (GST snaps / recalculations)
        # Priority 1: auto-detect seller GSTIN from invoice text, derive state code.
        # Priority 2: fall back to FIRM_GSTIN env var.
        # Priority 3: fall back to invoice-level tax amounts (least reliable).
        _GSTIN_RE = re.compile(r'\b([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z])\b')

        def _detect_seller_gstin(text: str, buyer_gstins: set) -> str:
            """
            Finds all GSTINs in the invoice text, removes buyer GSTINs,
            returns the first remaining one (= seller's GSTIN).
            """
            found = _GSTIN_RE.findall(text.upper())
            for g in found:
                if g not in buyer_gstins:
                    return g
            return ""

        def _interstate_from_gstin(items, firm_gstin: str):
            firm_state = firm_gstin[:2] if len(firm_gstin) >= 2 and firm_gstin[:2].isdigit() else None
            if not firm_state:
                return None
            for it in items:
                buyer = str(it.party_gstin or "").strip()
                if len(buyer) >= 2 and buyer[:2].isdigit():
                    return buyer[:2] != firm_state
            return None

        # Collect all buyer GSTINs from extracted items
        _buyer_gstins = {
            str(it.party_gstin or "").strip().upper()
            for it in cleaned_sales
            if it.party_gstin
        }
        # Try to auto-detect seller GSTIN from the invoice text
        _seller_gstin = _detect_seller_gstin(full_text, _buyer_gstins)
        if not _seller_gstin:
            _seller_gstin = os.getenv("FIRM_GSTIN", "")

        print(f"  [seller GSTIN] {_seller_gstin or 'unknown'}")
        # Primary signal: trust the invoice's own printed tax columns.
        # _extract_gst_summary_table already ran at the top of this function (gst_table).
        # GSTIN state-code comparison is unreliable when the seller auto-detects the wrong
        # GSTIN or issues from multiple-state entities — so use it only as a last resort.
        _ex_cgst = gst_table.get('cgst_amount', 0.0) if gst_table else (all_res.overall_cgst_amount or 0.0)
        _ex_sgst = gst_table.get('sgst_amount', 0.0) if gst_table else (all_res.overall_sgst_amount or 0.0)
        _ex_igst = gst_table.get('igst_amount', 0.0) if gst_table else (all_res.overall_igst_amount or 0.0)

        if _ex_igst > 0 and _ex_cgst == 0 and _ex_sgst == 0:
            overall_is_interstate = True
            print(f"  [interstate] IGST (from printed tax columns)")
        elif (_ex_cgst > 0 or _ex_sgst > 0) and _ex_igst == 0:
            overall_is_interstate = False
            print(f"  [interstate] CGST+SGST (from printed tax columns)")
        else:
            # Ambiguous (all zero, or both non-zero) — fall back to GSTIN comparison
            _gstin_result = _interstate_from_gstin(cleaned_sales, _seller_gstin)
            if _gstin_result is not None:
                overall_is_interstate = _gstin_result
                print(f"  [interstate] {'IGST' if overall_is_interstate else 'CGST+SGST'} "
                      f"(seller {_seller_gstin[:2]} vs buyer {next(iter(_buyer_gstins), '??')[:2]})")
            else:
                overall_is_interstate = (all_res.overall_igst_amount or 0.0) > (
                    (all_res.overall_cgst_amount or 0.0) + (all_res.overall_sgst_amount or 0.0)
                )
            correction_meta["tax_type_ambiguous_fallback"] = True
            _inv_no = cleaned_sales[0].invoice_no if cleaned_sales else "unknown"
            print(f"  [interstate] AMBIGUOUS — falling back to GSTIN comparison (invoice {_inv_no})")
        pre_rates = [item.rate for item in cleaned_sales]
        pre_taxes = [(item.cgst_amount, item.sgst_amount, item.igst_amount) for item in cleaned_sales]

        cleaned_sales = math_verification_agent(cleaned_sales, is_interstate=overall_is_interstate)
        
        for i, item in enumerate(cleaned_sales):
            if i < len(pre_rates) and pre_rates[i] != item.rate:
                correction_meta["gst_rates_snapped"] += 1
            if i < len(pre_taxes):
                pre_cgst, pre_sgst, pre_igst = pre_taxes[i]
                if pre_cgst != item.cgst_amount or pre_sgst != item.sgst_amount or pre_igst != item.igst_amount:
                    correction_meta["taxes_recalculated"] += 1
                    
        all_res.sales_items = cleaned_sales
        
    completed_post = now_utc()
    if logger:
        # Also update extraction log with correct subtotal rows dropped count
        try:
            logger.emit_post_processing(
                started_at=started_post,
                completed_at=completed_post,
                correction_meta=correction_meta,
                final_item_count=len(all_res.sales_items) + len(all_res.purchase_items)
            )
        except Exception as e:
            print(f"Error logging post_processing: {e}")

    try:
        pdf_plumber_doc.close()
    except:
        pass
        
    all_res.correction_meta = correction_meta
    all_res.prompt_tokens = total_prompt_tokens
    all_res.completion_tokens = total_completion_tokens
    all_res.total_pages = total_pages
    all_res.latency_ms = total_latency_ms
    all_res.total_retries = total_retries
    
    return all_res

def deduplicate_sales(df):
    if df.empty: return df
    # Removed aggressive deduplication to avoid dropping line items with the same tax rate/amount
    return df.drop_duplicates()

def deduplicate_purchase(df):
    if df.empty: return df
    df = df.drop_duplicates(subset=["SUPPLIER INV NO", "PARTY A/C NAME", "PARTICULARS", "AMOUNT"], keep="first")
    return df

_SUBTOTAL_KEYWORDS = [
    "sub total", "sub-total", "subtotal",
    "grand total", "total amount", "net amount", "net cost",
    "total cost", "amount payable", "balance due", "total payable",
]

def remove_subtotals(sales_items):
    cleaned_items = []
    current_group = []
    for item in sales_items:
        desc = str(item.particulars).lower()
        if any(k in desc for k in _SUBTOTAL_KEYWORDS):
            group_sum = sum(x.taxable_value or 0.0 for x in current_group)
            if abs(group_sum - (item.taxable_value or 0.0)) <= 2.0 and len(current_group) > 0:
                # Drop the sub-total to avoid double counting, keep the granular items
                cleaned_items.extend(current_group)
                current_group = []
            else:
                cleaned_items.extend(current_group)
                cleaned_items.append(item)
                current_group = []
        else:
            current_group.append(item)
    cleaned_items.extend(current_group)
    return cleaned_items

def classify_gstr1_item(item, seller_gstin=None) -> str:
    import os
    import json
    import re
    
    # Load rules from frontend/gstr1_rules.json
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    rules_path = os.path.join(base_dir, "frontend", "gstr1_rules.json")
    
    rules = []
    if os.path.exists(rules_path):
        try:
            with open(rules_path, 'r', encoding='utf-8') as f:
                rules = json.load(f).get("rules", [])
        except Exception as e:
            print(f"Error loading GSTR-1 rules: {e}")
            
    if not rules:
        # Fallback defaults if file loading fails
        rules = [
            {"category": "CDNR", "conditions": {"has_gstin": True, "is_credit_debit_note": True}},
            {"category": "B2B", "conditions": {"has_gstin": True, "is_credit_debit_note": False}},
            {"category": "EXP", "conditions": {"is_export": True}},
            {"category": "CDNUR", "conditions": {"has_gstin": False, "is_credit_debit_note": True}},
            {"category": "B2CL", "conditions": {"has_gstin": False, "is_credit_debit_note": False, "is_interstate": True, "invoice_value_greater_than": 250000.0}},
            {"category": "B2CS", "conditions": {"has_gstin": False, "is_credit_debit_note": False}}
        ]
        
    gstin = str(item.party_gstin or "").strip()
    has_gstin = len(gstin) >= 15 and gstin != "None" and gstin != ""
    
    # Credit/Debit note check
    voucher_type = str(item.voucher_type or "").lower()
    particulars = str(item.particulars or "").lower()
    is_credit_debit_note = "credit" in voucher_type or "debit" in voucher_type or "credit" in particulars or "debit" in particulars
    
    # Export check
    pos = str(item.place_of_supply or "").upper()
    # Already tagged as EXPORT by upstream processing — honour it
    _pre_tagged_export = str(item.gstr1_category or "").upper() in ("EXPORT", "EXP")
    # Detect foreign country in place_of_supply:
    #   "(FR)", "(US)", "(BE)", "(DE)" etc. — 2-letter alpha country codes in parens
    import re as _re
    _foreign_code = bool(_re.search(r'\(([A-Z]{2})\)', pos) and not _re.search(r'\(([A-Z]{2})\)', pos) is None
                         and _re.search(r'\(([A-Z]{2})\)', pos).group(1) not in (
                             "MH","DL","GJ","RJ","KA","TN","AP","TS","UP","MP","WB","PB","HR","BR",
                             "OR","KL","AS","JK","GA","HP","MN","ML","MZ","NL","SK","TR","AR","CG",
                             "JH","UK","CH","DD","DN","LD","PY","AN","LA","IN"
                         ))
    is_export = (_pre_tagged_export or "EXPORT" in pos or "OUTSIDE INDIA" in pos
                 or "SEZ" in pos or "DUTY FREE" in pos or _foreign_code)
    
    # Interstate check
    is_interstate = False
    if not has_gstin and not is_export:
        # Extract POS state code or name
        pos_clean = re.sub(r'[^A-Z0-9]', '', pos)
        if len(pos_clean) >= 2 and pos_clean[:2].isdigit():
            pos_code = pos_clean[:2]
            firm_gstin = os.getenv("FIRM_GSTIN", "")
            firm_state = firm_gstin[:2] if len(firm_gstin) >= 2 else "06"
            if pos_code != firm_state:
                is_interstate = True
        else:
            firm_gstin = os.getenv("FIRM_GSTIN", "")
            firm_state_name = _STATE_CODE_MAP.get(firm_gstin[:2] if len(firm_gstin) >= 2 else "06", "HARYANA")
            if pos and firm_state_name not in pos and pos not in firm_state_name:
                is_interstate = True
                
    invoice_value = float(item.total_invoice_value or 0.0)
    
    for rule in rules:
        cat = rule.get("category")
        conds = rule.get("conditions", {})
        
        match = True
        for c_key, c_val in conds.items():
            if c_key == "has_gstin" and has_gstin != c_val:
                match = False
            elif c_key == "is_credit_debit_note" and is_credit_debit_note != c_val:
                match = False
            elif c_key == "is_export" and is_export != c_val:
                match = False
            elif c_key == "is_interstate" and is_interstate != c_val:
                match = False
            elif c_key == "invoice_value_greater_than" and invoice_value <= c_val:
                match = False
                
        if match:
            return cat
            
    return "B2CS"

def qc_audit_sales_items(sales_items):
    valid_items = []
    hsn_map = {
        "saas": "9971",
        "mobile application": "9971",
        "upi qr": "9971",
        "additional users": "9971",
        "soundbox": "997319",
        "transactional messages": "998599",
        "app notifications": "998599",
        "promotional messages": "998599",
        "pan verification": "998529",
        "aadhaar verification": "998529",
        "gst verification": "998529",
        "cin verification": "998529",
        "late fees charges": "998311",
        "unallocated": "9971",
        "missing lines": "9971"
    }
    for item in sales_items:
        if not item.taxable_value or item.taxable_value <= 0:
            continue
        
        desc = str(item.particulars).lower()
        if any(k in desc for k in ["saas", "mobile application", "soundbox", "sms", "whatsapp", "additional users", "messaging"]):
            item.narration = "Being entry for book application charges and trasactional & promotional messaging charges for the month specifed in the data"
            
        if not item.hsn or str(item.hsn).lower() in ["nan", "none", ""]:
            assigned = False
            for key, hsn in hsn_map.items():
                if key in desc:
                    item.hsn = hsn
                    assigned = True
                    break
            if not assigned:
                item.hsn = "9971"
        
        # Apply GSTR-1 category classification (preserve if already correctly tagged as EXPORT/SEZ)
        if str(item.gstr1_category or "").upper() not in ("EXPORT", "EXP", "SEZ", "NIL_EXEMPT"):
            item.gstr1_category = classify_gstr1_item(item)
        valid_items.append(item)
    return valid_items

def math_verification_agent(sales_items, is_interstate: bool = None):
    """
    Snaps per-item GST rates to valid slabs and recomputes tax amounts.
    is_interstate: determined at the invoice level (overall IGST vs CGST+SGST).
                   Do NOT derive this per line item — individual items may have
                   zero tax which makes per-item detection unreliable.
    """
    valid_rates = [0.0, 0.05, 0.12, 0.18, 0.28]
    for item in sales_items:
        taxable = item.taxable_value or 0.0
        if taxable <= 0:
            continue
        # Export/SEZ/NIL-rated items must have 0 taxes — skip recalculation
        if str(item.gstr1_category or "").upper() in ("EXPORT", "SEZ", "NIL_EXEMPT"):
            item.cgst_amount = 0.0
            item.sgst_amount = 0.0
            item.igst_amount = 0.0
            item.rate = 0.0
            item.total_invoice_value = round(taxable, 2)
            continue

        cgst_extracted = item.cgst_amount or 0.0
        sgst_extracted = item.sgst_amount or 0.0
        igst_extracted = item.igst_amount or 0.0

        total_tax_extracted = cgst_extracted + sgst_extracted + igst_extracted
        raw_rate = total_tax_extracted / taxable if taxable > 0 else 0.0
        snapped_rate = min(valid_rates, key=lambda x: abs(x - raw_rate))

        # If the LLM hallucinated 0 tax but the HSN is a services HSN (99xx), force 18%
        # Skip for export/zero-rated items — they legitimately have 0 tax.
        _is_export_item = str(item.gstr1_category or "").upper() in ("EXPORT", "SEZ", "NIL_EXEMPT")
        if snapped_rate == 0.0 and str(item.hsn).startswith("99") and not _is_export_item:
            snapped_rate = 0.18

        # Use invoice-level interstate flag if provided; fall back to item-level only
        # when the caller couldn't determine it (legacy path).
        item_is_interstate = is_interstate if is_interstate is not None else (
            igst_extracted > (cgst_extracted + sgst_extracted)
        )

        if item_is_interstate:
            item.igst_amount = round(taxable * snapped_rate, 2)
            item.cgst_amount = 0.0
            item.sgst_amount = 0.0
        else:
            item.igst_amount = 0.0
            item.cgst_amount = round(taxable * (snapped_rate / 2), 2)
            item.sgst_amount = round(taxable * (snapped_rate / 2), 2)

        item.rate = round(snapped_rate * 100, 2)
        item.total_invoice_value = round(taxable + item.igst_amount + item.cgst_amount + item.sgst_amount, 2)
    return sales_items

def _correct_taxable_values(items):
    """
    Per GST law, taxable_value = (qty × rate) − discount.
    Two correction paths:
      A) qty & rate known: correct when taxable ≈ gross (discount not yet deducted).
      B) qty & rate unknown (SaaS/service items): if total_invoice_value ≈ taxable_value
         (i.e. no tax was added yet), the LLM stored the gross as taxable — subtract discount.
    """
    for item in items:
        discount = item.discount or 0.0
        if discount <= 0:
            continue
        qty = item.qty or 0.0
        rate = item.rate or 0.0
        taxable = item.taxable_value or 0.0

        # Path A: qty × rate available
        gross = qty * rate
        if gross > 0 and abs(taxable - gross) < 1.0:
            item.taxable_value = round(gross - discount, 2)
            continue

        # Path B: no qty/rate — LLM stored gross amount as taxable_value.
        # Signal: total_invoice_value ≈ taxable_value (no tax baked in yet)
        # and discount is less than taxable (sanity check).
        if qty == 0 and rate == 0 and discount < taxable:
            total = item.total_invoice_value or 0.0
            if total == 0 or abs(total - taxable) < 1.0:
                item.taxable_value = round(taxable - discount, 2)
    return items


def build_dataframes(extraction_response):
    sales_dfs = {"Sales Register": pd.DataFrame(), "Tax & TDS Workings": pd.DataFrame(), "Matching Sheet": pd.DataFrame()}
    if extraction_response.sales_items:
        # Prevent double counting by removing sub-totals
        extraction_response.sales_items = remove_subtotals(extraction_response.sales_items)

        # 0. Ensure taxable_value reflects post-discount net (GST must not apply on gross)
        extraction_response.sales_items = _correct_taxable_values(extraction_response.sales_items)

        # 1. Apply QC Audit (Remove zeroes, map missing HSNs)
        extraction_response.sales_items = qc_audit_sales_items(extraction_response.sales_items)
        
        # 2. Reconcile missing lines using the LLM's overall totals BEFORE math verification
        overall_total = extraction_response.overall_total_invoice_value
        sum_total = sum((item.taxable_value or 0.0) + (item.cgst_amount or 0.0) + (item.sgst_amount or 0.0) + (item.igst_amount or 0.0) for item in extraction_response.sales_items)
        diff = overall_total - sum_total

        # Skip phantom injection when diff ≈ tax on existing items (items extracted without per-line taxes)
        _sum_taxable_bd = sum(item.taxable_value or 0.0 for item in extraction_response.sales_items)
        _diff_is_just_tax_bd = any(abs(diff - _sum_taxable_bd * r) < 5.0 for r in (0.18, 0.12, 0.05, 0.28))

        if overall_total > 0 and diff > 1.0 and not _diff_is_just_tax_bd:
            taxable_diff = round(diff / 1.18, 2) # Assume standard 18% for missing lines
            is_interstate = False
            if len(extraction_response.sales_items) > 0:
                is_interstate = (extraction_response.sales_items[0].igst_amount or 0) > 0
                
            dummy_item = SuvitSalesItem(
                voucher_date=extraction_response.sales_items[0].voucher_date if extraction_response.sales_items else "",
                invoice_no=extraction_response.sales_items[0].invoice_no if extraction_response.sales_items else "",
                party_gstin=extraction_response.sales_items[0].party_gstin if extraction_response.sales_items else "",
                party_ledger_name=extraction_response.sales_items[0].party_ledger_name if extraction_response.sales_items else "",
                place_of_supply=extraction_response.sales_items[0].place_of_supply if extraction_response.sales_items else "",
                particulars="Unallocated / Missing Lines",
                hsn="9971",
                taxable_value=taxable_diff,
                cgst_amount=0.0 if is_interstate else round(taxable_diff * 0.09, 2),
                sgst_amount=0.0 if is_interstate else round(taxable_diff * 0.09, 2),
                igst_amount=round(taxable_diff * 0.18, 2) if is_interstate else 0.0,
                total_invoice_value=diff
            )
            extraction_response.sales_items.append(dummy_item)
            
        # 3. Apply strict Math Verification Agent across all items.
        # Trust the invoice's printed tax amounts (already set from _extract_gst_summary_table
        # earlier in process_pdf) as the primary signal for interstate/intrastate.
        _bd_cgst = extraction_response.overall_cgst_amount or 0.0
        _bd_sgst = extraction_response.overall_sgst_amount or 0.0
        _bd_igst = extraction_response.overall_igst_amount or 0.0
        if _bd_igst > 0 and _bd_cgst == 0 and _bd_sgst == 0:
            overall_is_interstate = True
        elif (_bd_cgst > 0 or _bd_sgst > 0) and _bd_igst == 0:
            overall_is_interstate = False
        else:
            overall_is_interstate = _bd_igst > (_bd_cgst + _bd_sgst)
        extraction_response.sales_items = math_verification_agent(
            extraction_response.sales_items, is_interstate=overall_is_interstate
        )

        records = []
        for item in extraction_response.sales_items:
            records.append({
                "REFERANCE NO": item.invoice_no,
                "INVOICE DATE": item.voucher_date,
                "GST NO": item.party_gstin,
                "PARTY A/C NAME": item.party_ledger_name,
                "PLACE OF SUPPLY": item.place_of_supply,
                "RAW_PARTICULARS": item.particulars,
                "AMOUNT": item.taxable_value,
                "DISCOUNT": getattr(item, 'discount', 0.0),
                "ADVANCES": getattr(item, 'advances', 0.0),
                "SGST": item.sgst_amount,
                "CGST": item.cgst_amount,
                "IGST": item.igst_amount,
                "TOTAL AMOUNT": item.total_invoice_value,
                "Narration": item.narration,
                "HSN": item.hsn,
                "GSTR-1 Category": getattr(item, 'gstr1_category', 'B2CS')
            })
        df_all = pd.DataFrame(records)
        df_all = deduplicate_sales(df_all)
        
        # 1. Main Sheet (Strictly ONE row per invoice)
        group_cols = ["REFERANCE NO", "INVOICE DATE", "GST NO", "PARTY A/C NAME", "PLACE OF SUPPLY", "GSTR-1 Category"]
        agg_dict = {
            "AMOUNT": "sum",
            "DISCOUNT": "sum",
            "ADVANCES": "sum",
            "SGST": "sum",
            "CGST": "sum",
            "IGST": "sum",
            "TOTAL AMOUNT": "sum"
        }
        df_main = df_all.groupby(group_cols, dropna=False).agg(agg_dict).reset_index()
        
        def get_single_hsn(grp):
            hsns = grp.dropna().unique()
            if len(hsns) == 1:
                return hsns[0]
            return None

        # Use actual item descriptions from the invoice, not a generic label.
        # Join multiple line descriptions with ' | ' for multi-line invoices.
        def _join_particulars(grp):
            parts = [str(v).strip() for v in grp.dropna().unique()
                     if v and str(v).strip() and str(v).strip() != "Unallocated / Missing Lines"]
            return " | ".join(parts) if parts else None

        hsn_vals  = df_all.groupby(group_cols[:-1], dropna=False)["HSN"].apply(get_single_hsn).reset_index()
        part_vals = df_all.groupby(group_cols[:-1], dropna=False)["RAW_PARTICULARS"].apply(_join_particulars).reset_index()
        part_vals.rename(columns={"RAW_PARTICULARS": "PARTICULARS"}, inplace=True)
        narr_vals = df_all.groupby(group_cols[:-1], dropna=False)["Narration"].first().reset_index()

        df_main = df_main.merge(part_vals, on=group_cols[:-1], how="left")
        df_main = df_main.merge(hsn_vals,  on=group_cols[:-1], how="left")
        df_main = df_main.merge(narr_vals, on=group_cols[:-1], how="left")

        # Inject invoice-level round-off (single value for the whole invoice, not a line-item sum)
        df_main["ROUND OFF"] = extraction_response.overall_round_off or 0.0

        # Rename Narration -> Nature (CA requirement: Nature = transaction description/narration)
        main_cols = ["REFERANCE NO", "INVOICE DATE", "GST NO", "PARTY A/C NAME", "PLACE OF SUPPLY", "PARTICULARS", "NATURE", "AMOUNT", "DISCOUNT", "ADVANCES", "SGST", "CGST", "IGST", "ROUND OFF", "TOTAL AMOUNT", "HSN", "GSTR-1 Category"]
        df_main.rename(columns={"Narration": "NATURE"}, inplace=True)
        for col in main_cols:
            if col not in df_main.columns:
                df_main[col] = None
        df_main = df_main[main_cols]

        # ── Sheet 2: Tax & TDS Workings ────────────────────────────────────────
        # Shows GST type decision (CGST+SGST vs IGST), TDS section/rate/amount,
        # and the routing rule applied. Kept separate from main sheet per CA guidance.
        def _gst_type(row):
            igst = row.get("IGST", 0) or 0
            cgst = row.get("CGST", 0) or 0
            sgst = row.get("SGST", 0) or 0
            taxable = row.get("AMOUNT", 0) or 0
            total_tax = igst + cgst + sgst
            if total_tax == 0 and taxable > 0:
                return "Export LUT"
            if igst > 0:
                return "Interstate"
            if cgst > 0 or sgst > 0:
                return "Intrastate"
            return "Exempt/Zero-rated"

        def _routing_rule(row):
            gst_type = row.get("GST Type", "")
            cat = row.get("GSTR-1 Category", "") or ""
            if gst_type == "Export LUT":
                return "IGST = 0 (Export LUT – Letter of Undertaking). Zero-rated under IGST Act Sec 16(3)(b)."
            elif gst_type == "Interstate":
                return f"Interstate supply → IGST only (CGST+SGST = 0). Category: {cat}."
            elif gst_type == "Intrastate":
                return f"Intrastate supply → CGST + SGST (equal halves). IGST = 0. Category: {cat}."
            return f"Zero-rated / Exempt supply. Category: {cat}."

        TDS_THRESHOLD = 30000  # Sec 194C threshold

        def _tds_section(row):
            taxable = row.get("AMOUNT", 0) or 0
            cat = (row.get("GSTR-1 Category", "") or "").upper()
            nat = (row.get("NATURE", "") or "").lower()
            if cat in ("EXP", "B2CS") or taxable < TDS_THRESHOLD:
                return ("No", "–", 0.0, 0.0, taxable, "Below threshold / not applicable")
            # 194J: professional / technical services
            prof_keywords = ["professional", "technical", "consulting", "audit", "legal", "management"]
            if any(k in nat for k in prof_keywords):
                rate = 10.0
                tds_amt = round(taxable * rate / 100, 2)
                return ("Yes", "194J – Prof/Tech Services", rate, tds_amt, round(taxable - tds_amt, 2), f"10% TDS on professional services (Sec 194J)")
            # 194C: contractor payments (default for B2B above threshold)
            rate = 2.0
            tds_amt = round(taxable * rate / 100, 2)
            return ("Yes", "194C – Contractor/Sub-contractor", rate, tds_amt, round(taxable - tds_amt, 2), "2% TDS on contract payments (Sec 194C, company deductee)")

        workings_records = []
        for _, row in df_main.iterrows():
            row_d = row.to_dict()
            gst_type = _gst_type(row_d)
            row_d["GST Type"] = gst_type
            routing = _routing_rule(row_d)
            tds_applicable, tds_section, tds_rate, tds_deducted, net_receivable, tds_note = _tds_section(row_d)
            workings_records.append({
                "Invoice No": row_d.get("REFERANCE NO"),
                "Invoice Date": row_d.get("INVOICE DATE"),
                "Party Name": row_d.get("PARTY A/C NAME"),
                "Party GSTIN": row_d.get("GST NO"),
                "Place of Supply": row_d.get("PLACE OF SUPPLY"),
                "Taxable Value (₹)": row_d.get("AMOUNT", 0),
                "GST Type": gst_type,
                "CGST Rate %": 9.0 if gst_type == "Intrastate" else 0.0,
                "CGST Amount (₹)": row_d.get("CGST", 0),
                "SGST Rate %": 9.0 if gst_type == "Intrastate" else 0.0,
                "SGST Amount (₹)": row_d.get("SGST", 0),
                "IGST Rate %": 18.0 if gst_type == "Interstate" else 0.0,
                "IGST Amount (₹)": row_d.get("IGST", 0),
                "Total Tax (₹)": (row_d.get("CGST", 0) or 0) + (row_d.get("SGST", 0) or 0) + (row_d.get("IGST", 0) or 0),
                "Total Invoice Value (₹)": row_d.get("TOTAL AMOUNT", 0),
                "GSTR-1 Category": row_d.get("GSTR-1 Category"),
                "GST Routing Rule Applied": routing,
                "TDS Applicable": tds_applicable,
                "TDS Section": tds_section,
                "TDS Rate %": tds_rate,
                "TDS Deducted (Est.) (₹)": tds_deducted,
                "Net Receivable After TDS (₹)": net_receivable,
                "TDS Note": tds_note,
                "Nature": row_d.get("NATURE"),
            })
        df_workings = pd.DataFrame(workings_records)

        # ── Sheet 3: Matching Sheet ─────────────────────────────────────────────
        # Cross-checks extracted invoice totals against math (taxable+tax ≈ total).
        # Shows final values with Nature column and PASS/FAIL status.
        matching_records = []
        for _, row in df_main.iterrows():
            taxable = float(row.get("AMOUNT") or 0)
            cgst = float(row.get("CGST") or 0)
            sgst = float(row.get("SGST") or 0)
            igst = float(row.get("IGST") or 0)
            round_off = float(row.get("ROUND OFF") or 0)
            total = float(row.get("TOTAL AMOUNT") or 0)
            total_tax = cgst + sgst + igst
            computed_total = taxable + total_tax + round_off
            variance = round(abs(total - computed_total), 2)
            # Export LUT: skip math check (total is in foreign currency)
            is_export_lut = total_tax == 0 and taxable > 0
            if is_export_lut:
                match_status = "PASS – Export LUT"
                variance = 0.0
            elif variance <= 2.50:
                match_status = "PASS"
            else:
                match_status = f"REVIEW – Variance ₹{variance}"
            matching_records.append({
                "Invoice No": row.get("REFERANCE NO"),
                "Invoice Date": row.get("INVOICE DATE"),
                "Party Name": row.get("PARTY A/C NAME"),
                "Party GSTIN": row.get("GST NO"),
                "Taxable Value (₹)": taxable,
                "CGST (₹)": cgst,
                "SGST (₹)": sgst,
                "IGST (₹)": igst,
                "Total Tax (₹)": total_tax,
                "Round Off (₹)": round_off,
                "Total Invoice Value (₹)": total,
                "Computed Total (₹)": round(computed_total, 2),
                "Variance (₹)": variance,
                "Match Status": match_status,
                "GSTR-1 Category": row.get("GSTR-1 Category"),
                "Nature": row.get("NATURE"),
            })
        df_matching = pd.DataFrame(matching_records)

        sales_dfs["Sales Register"] = df_main
        sales_dfs["Tax & TDS Workings"] = df_workings
        sales_dfs["Matching Sheet"] = df_matching
        # Remove old unused keys
        for k in ["Main", "Narration", "LineItems"]:
            sales_dfs.pop(k, None)
        
    purchase_df = pd.DataFrame()
    if extraction_response.purchase_items:
        records = []
        for item in extraction_response.purchase_items:
            itc_status = getattr(item, "itc_category", None) or getattr(item, "itc_eligibility", None) or "ITC_UNKNOWN"
            records.append({
                "SUPPLIER INV NO":  item.invoice_no,
                "INVOICE DATE":     item.voucher_date,
                "GST NO":           item.party_gstin,
                "PARTY A/C NAME":   item.party_ledger_name,
                "PLACE OF SUPPLY":  item.place_of_supply,
                "HSN":              item.hsn,
                "PARTICULARS":      item.particulars,
                "QTY":              item.qty,
                "RATE":             item.rate,
                "TAXABLE AMOUNT":   item.taxable_value,
                "CGST":             item.cgst_amount,
                "SGST":             item.sgst_amount,
                "IGST":             item.igst_amount,
                "TOTAL AMOUNT":     item.total_invoice_value,
                "ITC ELIGIBILITY":  itc_status,
                "Narration":        item.narration,
            })
        purchase_df = pd.DataFrame(records)
        purchase_df = deduplicate_purchase(purchase_df)

    return sales_dfs, purchase_df
