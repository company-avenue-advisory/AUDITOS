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
    if model_override and model_override.get("provider") == "openrouter":
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
        # Default to Groq if key is present, else Gemini
        if os.getenv("GROQ_API_KEY"):
            model_name = "llama-3.3-70b-versatile"
            base_url = "https://api.groq.com/openai/v1"
            api_key = os.getenv("GROQ_API_KEY")
        else:
            model_name = "gemini-2.5-flash"
            base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
            api_key = os.getenv("GEMINI_API_KEY", "")
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
        provider=model_override.get("provider") if model_override else ("groq" if os.getenv("GROQ_API_KEY") else "google_native"),
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
        "unallocated_row_details": {}
    }
    
    if all_res.sales_items:
        # Detect subtotal rows dropped
        orig_len = len(all_res.sales_items)
        cleaned_sales = remove_subtotals(all_res.sales_items)
        dropped = orig_len - len(cleaned_sales)
        correction_meta["subtotal_rows_dropped"] = dropped
        
        # Ensure taxable_value reflects post-discount net
        cleaned_sales = _correct_taxable_values(cleaned_sales)

        # Apply QC Audit
        cleaned_sales = qc_audit_sales_items(cleaned_sales)

        # Unallocated variance injection
        overall_total = all_res.overall_total_invoice_value
        sum_total = sum((item.taxable_value or 0.0) + (item.cgst_amount or 0.0) + (item.sgst_amount or 0.0) + (item.igst_amount or 0.0) for item in cleaned_sales)
        diff = overall_total - sum_total
        
        if overall_total > 0 and diff > 1.0:
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
        # Determine interstate from invoice-level totals — per-item detection fails when
        # line items carry 0 tax (e.g. advance-deducted invoices like Digitap/OneStack).
        overall_is_interstate = (all_res.overall_igst_amount or 0.0) > (
            (all_res.overall_cgst_amount or 0.0) + (all_res.overall_sgst_amount or 0.0)
        )
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

def remove_subtotals(sales_items):
    cleaned_items = []
    current_group = []
    for item in sales_items:
        desc = str(item.particulars).lower()
        if "sub total" in desc or "sub-total" in desc or "subtotal" in desc:
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
    is_export = "EXPORT" in pos or "OUTSIDE INDIA" in pos or "SEZ" in pos or "DUTY FREE" in pos
    
    # Interstate check
    is_interstate = False
    if not has_gstin and not is_export:
        # Extract POS state code or name
        pos_clean = re.sub(r'[^A-Z0-9]', '', pos)
        if len(pos_clean) >= 2 and pos_clean[:2].isdigit():
            pos_code = pos_clean[:2]
            # One Stack GSTIN typically starts with 08 (Haryana), if not 08 it is interstate
            if pos_code != "08":
                is_interstate = True
        else:
            if pos and "HARYANA" not in pos and "HR" not in pos:
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
        
        # Apply GSTR-1 category classification
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

        cgst_extracted = item.cgst_amount or 0.0
        sgst_extracted = item.sgst_amount or 0.0
        igst_extracted = item.igst_amount or 0.0

        total_tax_extracted = cgst_extracted + sgst_extracted + igst_extracted
        raw_rate = total_tax_extracted / taxable if taxable > 0 else 0.0
        snapped_rate = min(valid_rates, key=lambda x: abs(x - raw_rate))

        # If the LLM hallucinated 0 tax but the HSN is a services HSN (99xx), force 18%
        if snapped_rate == 0.0 and str(item.hsn).startswith("99"):
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
    If the LLM returned the gross amount when a discount exists, fix it here
    so that CGST/SGST/IGST are applied on the correct net value.
    """
    for item in items:
        discount = item.discount or 0.0
        if discount <= 0:
            continue
        qty = item.qty or 0.0
        rate = item.rate or 0.0
        gross = qty * rate
        taxable = item.taxable_value or 0.0
        # If taxable_value looks like the gross (discount not yet deducted), correct it
        if gross > 0 and abs(taxable - gross) < 1.0:
            item.taxable_value = round(gross - discount, 2)
    return items


def build_dataframes(extraction_response):
    sales_dfs = {"Main": pd.DataFrame(), "Narration": pd.DataFrame(), "LineItems": pd.DataFrame()}
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
        
        if overall_total > 0 and diff > 1.0:
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
            
        # 3. Apply strict Math Verification Agent across all items
        overall_is_interstate = (extraction_response.overall_igst_amount or 0.0) > (
            (extraction_response.overall_cgst_amount or 0.0) + (extraction_response.overall_sgst_amount or 0.0)
        )
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
        
        def get_particulars(row):
            return "Sales IGST 18" if row.get("IGST", 0) > 0 else "Sales GST 18"
            
        df_main["PARTICULARS"] = df_main.apply(get_particulars, axis=1)
        
        def get_single_hsn(grp):
            hsns = grp.dropna().unique()
            if len(hsns) == 1:
                return hsns[0]
            return None
            
        hsn_vals = df_all.groupby(group_cols[:-1], dropna=False)["HSN"].apply(get_single_hsn).reset_index()
        narr_vals = df_all.groupby(group_cols[:-1], dropna=False)["Narration"].first().reset_index()
        
        df_main = df_main.merge(hsn_vals, on=group_cols[:-1], how="left")
        df_main = df_main.merge(narr_vals, on=group_cols[:-1], how="left")

        # Inject invoice-level round-off (single value for the whole invoice, not a line-item sum)
        df_main["ROUND OFF"] = extraction_response.overall_round_off or 0.0

        main_cols = ["REFERANCE NO", "INVOICE DATE", "GST NO", "PARTY A/C NAME", "PLACE OF SUPPLY", "PARTICULARS", "AMOUNT", "DISCOUNT", "ADVANCES", "SGST", "CGST", "IGST", "ROUND OFF", "TOTAL AMOUNT", "Narration", "HSN", "GSTR-1 Category"]
        for col in main_cols:
            if col not in df_main.columns:
                df_main[col] = None
        df_main = df_main[main_cols]
        
        # 2. Narration Sheet
        df_narration = df_all.groupby("REFERANCE NO", dropna=False).agg({"TOTAL AMOUNT": "sum", "Narration": "first"}).reset_index()
        df_narration.rename(columns={"TOTAL AMOUNT": "Final Total"}, inplace=True)
        df_narration = df_narration[["Narration", "Final Total"]]
        
        # 3. Line Items Sheet
        df_line = df_all.copy()
        df_line.rename(columns={"RAW_PARTICULARS": "Particulars / Item Description"}, inplace=True)
        
        sales_dfs["Main"] = df_main
        sales_dfs["Narration"] = df_narration
        sales_dfs["LineItems"] = df_line
        
    purchase_df = pd.DataFrame()
    if extraction_response.purchase_items:
        records = []
        for item in extraction_response.purchase_items:
            records.append({
                "SUPPLIER INV NO": item.invoice_no,
                "INVOICE DATE": item.voucher_date,
                "GST NO": item.party_gstin,
                "PARTY A/C NAME": item.party_ledger_name,
                "PLACE OF SUPPLY": item.place_of_supply,
                "PARTICULARS": item.particulars,
                "AMOUNT": item.taxable_value,
                "SGST": item.sgst_amount,
                "CGST": item.cgst_amount,
                "IGST": item.igst_amount,
                "TOTAL AMOUNT": item.total_invoice_value,
                "Narration": item.narration,
                "HSN": item.hsn
            })
        purchase_df = pd.DataFrame(records)
        purchase_df = deduplicate_purchase(purchase_df)
        
    return sales_dfs, purchase_df
