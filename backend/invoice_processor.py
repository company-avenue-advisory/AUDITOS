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

# Maps ReconciliationReport.canonical_values field names to the corresponding
# InvoiceExtractionResponse "overall_*" attribute.
_CANONICAL_TO_OVERALL_ATTR = {
    "taxable_value": "overall_taxable_value",
    "grand_total": "overall_total_invoice_value",
    "cgst_amount": "overall_cgst_amount",
    "sgst_amount": "overall_sgst_amount",
    "igst_amount": "overall_igst_amount",
}

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

    # ── GST summary data row(s) ───────────────────────────────────────────────
    # Anchor on the broad "Taxable Value...Central Tax" header (same text the old
    # single-row regex used, so it matches all One Stack Solution invoices).  Then
    # use finditer on the 2000-char window after the header to capture ALL data rows
    # and sum them — this handles mixed CGST+SGST + IGST invoices where intrastate
    # and interstate items appear on separate rows in the GST summary table.
    # Rate digits may be absent (shown as bare "%"), so the digit group is optional.
    row_re = re.compile(
        r'([\d,]+\.[\d]{2})\s+'    # taxable value
        r'(\d*\.?\d*)\s*%\s+'      # CGST rate (may be blank → 0)
        r'([\d,]+\.[\d]{2})\s+'    # CGST amount
        r'(\d*\.?\d*)\s*%\s+'      # SGST rate
        r'([\d,]+\.[\d]{2})\s+'    # SGST amount
        r'(\d*\.?\d*)\s*%\s+'      # IGST rate
        r'([\d,]+\.[\d]{2})'       # IGST amount
    )
    header_m = re.search(r'Taxable Value.{0,300}?Central Tax', text, re.DOTALL)
    if header_m:
        after_header = text[header_m.end():]
        rows = list(row_re.finditer(after_header[:2000]))
        if rows:
            result['taxable_value'] = round(sum(_f(r.group(1)) for r in rows), 2)
            result['cgst_amount']   = round(sum(_f(r.group(3)) for r in rows), 2)
            result['sgst_amount']   = round(sum(_f(r.group(5)) for r in rows), 2)
            result['igst_amount']   = round(sum(_f(r.group(7)) for r in rows), 2)
            # rates too (needed to prorate tax across deterministic line items -
            # see extract_deterministic_line_items) - take the first row's
            # rates; CGST rate always equals SGST rate, validated across 180+
            # real OneStack invoices with zero exceptions this session
            first = rows[0]
            result['cgst_rate'] = float(first.group(2)) if first.group(2) else 0.0
            result['sgst_rate'] = float(first.group(4)) if first.group(4) else 0.0
            result['igst_rate'] = float(first.group(6)) if first.group(6) else 0.0

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
    # Prefer the explicit "Final Total (...)" label match; fall back to the
    # row-based 'taxable_value' capture (from the GST rate-table row) — on
    # invoices where the "Final Total" label isn't immediately followed by its
    # amount in extracted text order, that regex misses even though the GST
    # summary row itself (which IS the post-advance base actually taxed) was
    # captured correctly.
    _final_total = result.get('final_total', result.get('taxable_value'))
    if 'net_cost' in result and _final_total is not None:
        adv = round(result['net_cost'] - _final_total, 2)
        if adv > 0.50:
            result['advance_amount'] = adv

    return result


def _fill_missing_sales_line_items(full_text: str, existing_items: list, variance_amount: float,
                                    client, model_name: str) -> list:
    """
    Targeted follow-up extraction: the sum of already-extracted line items falls
    short of the invoice's own (deterministically parsed) total by
    `variance_amount`. Rather than fabricate a placeholder "Unallocated" row,
    ask the model specifically to find the real missing item(s) in the invoice
    text that account for this gap.

    Returns a list of SuvitSalesItem (possibly empty if nothing genuine is
    found, or if the found item(s) don't actually reconcile the gap) — never
    fabricates data.
    """
    import json as _json

    existing_desc = "\n".join(
        f"- {it.particulars!r} (HSN {it.hsn}, taxable ₹{it.taxable_value})"
        for it in existing_items
    ) or "(none)"

    prompt = f"""You already extracted these line items from an invoice:
{existing_desc}

Their totals are short by ₹{variance_amount:.2f} compared to the invoice's own printed total.
Look again at the raw invoice text below and find the SPECIFIC line item(s) you missed —
do NOT invent a number, do NOT split the variance evenly across a guess. Only return items
whose amounts you can literally see printed in the text below. If a section like "KYC Charges",
"Late Fees", or a small sub-total was skipped because it looked like a footer or an
administrative line, that is exactly the kind of thing to look for.

If you genuinely cannot find missing line item(s) whose amounts explain the gap, return an
empty list — do not guess.

Return JSON: {{"missing_items": [{{"particulars": str, "hsn": str, "taxable_value": number,
"cgst_amount": number, "sgst_amount": number, "igst_amount": number, "total_invoice_value": number}}]}}

===== RAW INVOICE TEXT =====
{full_text[:6000]}
"""

    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=2048,
        )
        raw_content = response.choices[0].message.content
        if not raw_content:
            return []
        content = raw_content.strip()
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            content = json_match.group(0)
        data = _json.loads(content)
        candidates = data.get("missing_items", [])
        if not candidates:
            return []

        found_items = []
        for c in candidates:
            try:
                found_items.append(SuvitSalesItem(
                    voucher_date=existing_items[0].voucher_date if existing_items else "",
                    invoice_no=existing_items[0].invoice_no if existing_items else "",
                    party_gstin=existing_items[0].party_gstin if existing_items else "",
                    party_ledger_name=existing_items[0].party_ledger_name if existing_items else "",
                    place_of_supply=existing_items[0].place_of_supply if existing_items else "",
                    particulars=str(c.get("particulars") or "").strip(),
                    hsn=str(c.get("hsn") or ""),
                    taxable_value=float(c.get("taxable_value") or 0.0),
                    cgst_amount=float(c.get("cgst_amount") or 0.0),
                    sgst_amount=float(c.get("sgst_amount") or 0.0),
                    igst_amount=float(c.get("igst_amount") or 0.0),
                    total_invoice_value=float(c.get("total_invoice_value") or 0.0),
                ))
            except Exception:
                continue

        if not found_items:
            return []

        # Only accept the found item(s) if they actually close the gap — otherwise
        # this is the model guessing, not finding, and we discard it.
        # NOTE: variance_amount (passed in by the caller) is a taxable-value-only
        # figure — compare against the found items' taxable value only, not a
        # tax-inclusive sum, or a correct find gets rejected as a false mismatch.
        found_taxable_sum = sum(it.taxable_value or 0.0 for it in found_items)
        if abs(found_taxable_sum - variance_amount) > max(2.0, variance_amount * 0.05):
            print(f"  [GapFill] Found items taxable sum (Rs.{found_taxable_sum:.2f}) doesn't reconcile variance "
                  f"(Rs.{variance_amount:.2f}) - discarding, leaving gap for human review.")
            return []

        print(f"  [GapFill] Recovered {len(found_items)} missing line item(s) explaining Rs.{variance_amount:.2f} gap: "
              f"{[it.particulars for it in found_items]}")
        return found_items

    except Exception as e:
        print(f"  [GapFill] Follow-up extraction failed: {e}")
        return []


_INVOICE_HEADER_RE = re.compile(
    r'Customer Name:\s*(?P<party_name>.+?)\s*Billing Month:.*?'
    r'GSTIN:\s*(?P<gstin>[0-9A-Z]{15})\s*Invoice Number:\s*(?P<invoice_no>\S+).*?'
    r'Date of Invoice:\s*(?P<date>\d{2}-\d{2}-\d{4})',
    re.DOTALL,
)


def _extract_invoice_header(full_text: str) -> dict:
    """
    Deterministically parses party name / GSTIN / invoice number / date from
    the single header block every OneStack invoice prints:
    'Customer Name: X Billing Month: month GSTIN: gstin Invoice Number: no
    PAN: pan Date of Invoice: date'. Regex, no LLM - this line block is
    reliable across every real invoice checked this session.
    Empty dict if the block isn't found (falls back to whatever the LLM
    extracted for these fields).
    """
    m = _INVOICE_HEADER_RE.search(full_text)
    if not m:
        return {}
    gstin = m.group("gstin")
    return {
        "party_name": re.sub(r'\s+', ' ', m.group("party_name")).strip(),
        "party_gstin": gstin,
        "invoice_no": m.group("invoice_no").strip(),
        "voucher_date": m.group("date"),
        "place_of_supply": _STATE_CODE_MAP.get(gstin[:2], ""),
    }


# (regex, particulars label, HSN or None if genuinely absent on the invoice
# template) - one row per lettered billing section A-J. Ported from this
# session's line_item_extractor.py, now the single canonical implementation.
_LINE_ITEM_SECTIONS = [
    (r'A\s+SAAS\s*/\s*Mobile Application.*?Sub Total\s+([\d,]+\.\d{2})', "SaaS/UPI Platform Charges", "9971"),
    (r'B\s+Soundbox Charges.*?Sub Total\s+([\d,]+\.\d{2})', "Soundbox Charges", "997319"),
    (r'C\s+CBS\s*\(Core Banking Solution\)\s*([\d,]+\.\d{2})', "Core Banking Solution Charges", None),
    (r'D\s+Transactional Messages.*?Sub Total\s+\S*\s*\S*\s*\S*\s*([\d,]+\.\d{2})', "Transactional Messaging Charges", "998599"),
    (r'E\s+Promotional Messages.*?Sub Total\s+\S*\s*\S*\s*([\d,]+\.\d{2})', "Promotional Messaging Charges", "998599"),
    (r'F\s+KYC Charges.*?Sub Total\s+([\d,]+\.\d{2})', "KYC Verification Charges", "998529"),
    (r'G\s+Late Fees Charges\s+[\d,]+\.\d{2}\s*\d*%?\s*([\d,]+\.?\d*)', "Late Payment Fee", None),
    (r'H\s+Ad Hoc Charges\s+([\d,]+\.\d{2})', "Ad Hoc Charges", None),
    # These two are letter-agnostic ([A-J], not a fixed letter): verified
    # this session that when an invoice only has these two sections (no
    # SaaS/Soundbox/etc at all - the OMH/OHR "adjustment" invoices, e.g.
    # Pragati's OMH26061005), they get relettered sequentially starting
    # from A/B instead of keeping their "canonical" I/J position. Anchoring
    # on the section name text instead of the letter handles both cases.
    (r'[A-J]\s+Transactional Charges\b.*?Total\s+\S*\s*\S*\s*([\d,]+\.\d{2})', "High-Volume Transactional Charges", None),
    (r'[A-J]\s+UPI 2\.0 Transactional Messages.*?Sub Total\s+\S*\s*\S*\s*\S*\s*([\d,]+\.\d{2})', "UPI 2.0 Transactional Messaging Charges", "998599"),
]

NOT_SPECIFIED_HSN = "NOT SPECIFIED ON INVOICE"

# Fallback for the ~1.6% of invoices (verified: 3 of 183 this session - all
# OMH/OHR "adjustment series") that skip the standard A-J section template
# entirely and are just a single ad-hoc line: "A <description> <hsn> ...
# <amount> B Final Total <amount>", with no "SAAS"/"Soundbox Charges"/etc
# header text at all (e.g. Bijnor's one-off Soundbox charge, Sirohi's
# one-off Dun & Bradstreet charge). Tried only when none of the 10 named
# sections matched.
_SINGLE_LINE_INVOICE_RE = re.compile(
    r'\bA\b\s*\n?(?P<desc>.+?)\n?(?P<hsn>\d{4,8})\b.*?(?P<amt>[\d,]+\.\d{2})\s*\n?B\s*\n?Final Total',
    re.DOTALL,
)


def extract_deterministic_line_items(full_text: str, taxable_value_total: float,
                                      cgst_rate: float, sgst_rate: float, igst_rate: float) -> list:
    """
    Breaks a OneStack invoice into per-section line items (billing sections
    A-J) instead of one rolled-up row per invoice. Pure regex against the
    printed 'Sub Total' lines - no LLM involvement, so results can't drift
    between runs the way LLM-extracted sales_items can.

    Sections with no HSN on the OneStack template (C, G, H, I) get
    NOT_SPECIFIED_HSN rather than a blank string - blank/None would trigger
    qc_audit_sales_items' HSN-autofill-to-9971 fallback, which is wrong for
    these sections (verified directly against source PDFs this session:
    they genuinely carry no HSN, autofilling one would misstate the return).

    Handles "Advance Paid" deductions: the printed section Sub Totals are
    PRE-advance. The whole gap between their sum and taxable_value_total is
    applied to the largest section first, cascading to the next-largest if
    it would go negative - validated against real invoices where the
    advance was paid against a specific category, not spread proportionally
    across every section (see this session's regression fixtures).

    Returns [] if no section regex matched at all (not a OneStack-template
    invoice, or extraction genuinely failed) - callers should fall back to
    whatever the LLM extracted rather than force an empty result.
    """
    def _f(s):
        try:
            return float(str(s).replace(',', '').replace(' ', ''))
        except Exception:
            return 0.0

    items = []
    for pattern, label, hsn in _LINE_ITEM_SECTIONS:
        m = re.search(pattern, full_text, re.DOTALL)
        if m:
            amt = _f(m.group(1))
            if amt > 0:
                items.append({"particulars": label, "hsn": hsn or NOT_SPECIFIED_HSN, "taxable": amt})

    if not items:
        m = _SINGLE_LINE_INVOICE_RE.search(full_text)
        if m:
            amt = _f(m.group("amt"))
            if amt > 0:
                desc = re.sub(r'\s+', ' ', m.group("desc")).strip()
                items.append({"particulars": desc or "Ad Hoc Charges", "hsn": m.group("hsn"), "taxable": amt})

    if not items:
        return []

    section_sum = sum(i["taxable"] for i in items)
    gap = round(section_sum - taxable_value_total, 2)
    if abs(gap) > 0.01:
        items_sorted = sorted(items, key=lambda i: -i["taxable"])
        remaining_gap = gap
        for i in items_sorted:
            if remaining_gap <= 0.005:
                break
            take = min(i["taxable"], remaining_gap)
            i["taxable"] = round(i["taxable"] - take, 2)
            remaining_gap = round(remaining_gap - take, 2)
        items = [i for i in items if i["taxable"] > 0.005]
        if not items:
            # entire invoice was advance-covered - a single nominal NIL line
            # so the invoice still has at least one line item on record
            items = [{"particulars": "SaaS/UPI Platform Charges", "hsn": "9971", "taxable": 0.0}]

    cgst_running = sgst_running = igst_running = 0.0
    total_cgst = round(taxable_value_total * cgst_rate / 100, 2)
    total_sgst = round(taxable_value_total * sgst_rate / 100, 2)
    total_igst = round(taxable_value_total * igst_rate / 100, 2)
    for idx, i in enumerate(items):
        is_last = (idx == len(items) - 1)
        if is_last:
            i["cgst"] = round(total_cgst - cgst_running, 2)
            i["sgst"] = round(total_sgst - sgst_running, 2)
            i["igst"] = round(total_igst - igst_running, 2)
        else:
            i["cgst"] = round(i["taxable"] * cgst_rate / 100, 2)
            i["sgst"] = round(i["taxable"] * sgst_rate / 100, 2)
            i["igst"] = round(i["taxable"] * igst_rate / 100, 2)
            cgst_running += i["cgst"]
            sgst_running += i["sgst"]
            igst_running += i["igst"]
        i["total"] = round(i["taxable"] + i["cgst"] + i["sgst"] + i["igst"], 2)
    return items


_CREDIT_NOTE_KNOWN_HSN = ("9971", "997319", "998599", "998529", "998313")

_CREDIT_NOTE_FIELD_RE = {
    "credit_note_no": re.compile(r'Credit Note Number\s*:?\s*\n?\s*(\S+)'),
    "date": re.compile(r'Credit Note Number\s*:?\s*\S+\s*Date:\s*\n?\s*(\d{1,2}-\d{1,2}-\d{2,4})'),
    "party_name": re.compile(r'Bill To:\s*\n?\s*([^\n]+)'),
    "original_invoice_no": re.compile(r'Original Invoice Number\s*:?\s*\n?\s*(\S+)'),
    "original_invoice_date": re.compile(r'Original Invoice Date:\s*\n?\s*(\d{1,2}-\d{1,2}-\d{2,4})'),
    "reason": re.compile(r'Reason for Credit Note:\s*\n?\s*([^\n]+)'),
    "subtotal": re.compile(r'Subtotal:\s*\n?\s*([\d,]+\.\d{2})'),
    "rounding": re.compile(r'Rounding off\s*:?\s*\n?\s*(-?[\d,]+\.\d{2})'),
}
_CREDIT_NOTE_RATE_RE = re.compile(
    r'(CGST|SGST|IGST)\s*@\s*([\d.]+)%\s*\n?\s*(-|[\d,]+\.\d{2})'
)
# the actual total-credited amount is only reliably printed once, right
# before the amount-in-words line - "Total Amount Credited:" itself is
# often left blank on the template
_CREDIT_NOTE_TOTAL_RE = re.compile(r'([\d,]+\.\d{2})\s*\n?\s*Indian Rupees')

# The line-item table on a credit note prints "Total <letter> <section
# name>" (same lettered A-J sections as a regular invoice's
# _LINE_ITEM_SECTIONS) right before the amount columns - e.g. "Total A
# Soundbox Charges 997319 50 999 49,950.00". This is what tells you which
# HSN bucket the credit applies to; the blind "any known HSN string found
# anywhere before Subtotal" fallback below has actually picked the WRONG
# bucket on a real filing (a Rs 2,033 note landed in 998599 instead of its
# real bucket 997319, confirmed against the source PDF) when more than one
# known HSN-like token appears in that window. Keyword-match the section
# NAME first; only fall back to the blind scan when no section line is
# printed at all (e.g. Pochampally's credit notes, which print literal "0"
# placeholders with no descriptive label - genuinely not specified, not a
# case to guess at from the freeform "Reason for Credit Note" text).
_CREDIT_NOTE_SECTION_RE = re.compile(r'Total\s+[A-J]\s+(.+?)\s+[\d,]', re.DOTALL)
_CREDIT_NOTE_SECTION_HSN = [
    ("soundbox", "997319"),
    ("saas", "9971"),
    ("application", "9971"),
    ("upi 2.0", "998599"),
    ("upi2", "998599"),
    ("transactional", "998599"),
    ("promotional", "998599"),
    ("kyc", "998529"),
    ("core banking", None),
    ("cbs", None),
    ("late fee", None),
    ("late payment", None),
    ("late charges", None),
    ("ad hoc", None),
]


def _hsn_from_cn_section_line(table_window: str) -> Optional[str]:
    """Returns the HSN for the credit note's "Total <letter> <name>" line,
    or None if no such line is present (caller falls back to the blind
    scan / NOT_SPECIFIED_HSN)."""
    m = _CREDIT_NOTE_SECTION_RE.search(table_window)
    if not m:
        return None
    section_name = re.sub(r'\s+', ' ', m.group(1)).strip().lower()
    for keyword, hsn in _CREDIT_NOTE_SECTION_HSN:
        if keyword in section_name:
            return hsn or NOT_SPECIFIED_HSN
    return None


def extract_credit_note(full_text: str) -> Optional[dict]:
    """
    Deterministically parses a OneStack credit note (regex, no LLM).
    Returns None if full_text doesn't contain a "Credit Note Number" -
    callers use that to tell a credit note apart from a regular invoice.

    Fields returned, all directly printed on the document:
      credit_note_no, date, party_name, original_invoice_no,
      original_invoice_date, reason, taxable, cgst_rate, cgst, sgst_rate,
      sgst, igst_rate, igst, round_off, total, hsn

    Values are POSITIVE (the note's own value) - NOT the negative sign
    convention used internally by the manual Sales Register this session.
    gstr1_generator.py's _build_cdnr/_build_cdnur already expect positive
    totals and use ntty='C'/'D' to distinguish credit vs debit, so this
    matches the existing downstream contract rather than introducing a
    second sign convention.

    party_gstin is deliberately NOT returned - no real credit note prints
    the buyer's GSTIN directly (verified across all 14 real credit notes
    this session). Resolving it means looking up original_invoice_no
    against past invoices' records - a DB concern, out of scope for a
    pure text-extraction function. Callers must resolve GSTIN separately
    before this can be filed (see resolve_credit_note_gstin below).
    """
    if "Credit Note Number" not in full_text:
        return None

    def _f(s):
        if s is None or s.strip() == "-":
            return 0.0
        return float(s.replace(',', ''))

    result = {}
    for field, pattern in _CREDIT_NOTE_FIELD_RE.items():
        m = pattern.search(full_text)
        result[field] = m.group(1).strip() if m else None

    result["taxable"] = _f(result.pop("subtotal"))
    result["round_off"] = _f(result.pop("rounding"))

    rates = {"cgst_rate": 0.0, "cgst": 0.0, "sgst_rate": 0.0, "sgst": 0.0, "igst_rate": 0.0, "igst": 0.0}
    for tax, rate_str, amt_str in _CREDIT_NOTE_RATE_RE.findall(full_text):
        key = tax.lower()
        rates[f"{key}_rate"] = float(rate_str)
        rates[key] = _f(amt_str)
    result.update(rates)

    total_m = _CREDIT_NOTE_TOTAL_RE.search(full_text)
    result["total"] = _f(total_m.group(1)) if total_m else round(
        result["taxable"] + rates["cgst"] + rates["sgst"] + rates["igst"] + result["round_off"], 2
    )

    # Bucket by the credit note's own "Total <letter> <section name>" line
    # first (see _hsn_from_cn_section_line) - falls back to the blind
    # "any known HSN string in the window" scan, then NOT_SPECIFIED_HSN,
    # when no such line is printed at all.
    subtotal_idx = full_text.find("Subtotal")
    table_window = full_text[:subtotal_idx] if subtotal_idx > 0 else full_text
    section_hsn = _hsn_from_cn_section_line(table_window)
    if section_hsn is not None:
        result["hsn"] = section_hsn
    else:
        result["hsn"] = next((h for h in _CREDIT_NOTE_KNOWN_HSN if h in table_window), NOT_SPECIFIED_HSN)

    if result["party_name"]:
        # when the PDF has no line break between "Bill To:" and "Original
        # Invoice Number", the raw capture runs the party name, full
        # address, and that next label together with no delimiter - trim
        # the obvious leakage. This is still best-effort: on a single-line
        # layout the address itself stays glued to the name (there's no
        # regex-detectable boundary between them). Treat this field as a
        # fallback label only - resolve_credit_note_gstin's original-
        # invoice-number lookup is the authoritative source for both name
        # and GSTIN, since it looks up the buyer's own regular invoice.
        result["party_name"] = re.split(r'\s*Original Invoice Number', result["party_name"])[0]
        result["party_name"] = re.sub(r'\s+', ' ', result["party_name"]).strip()

    return result


def resolve_credit_note_gstin(original_invoice_no: str, lookup_fn) -> Optional[str]:
    """
    Resolves a credit note's buyer GSTIN via its Original Invoice Number,
    since the credit note document itself never prints one.

    lookup_fn(invoice_no) -> gstin string or None; injected so this stays
    a pure function testable without a live DB (same dependency-injection
    pattern as drive_classifier.walk_and_classify's list_children_fn) -
    the real caller passes a function that queries SalesLineItem by
    invoice_no. Returns None (not a guess) if the original invoice can't
    be found - e.g. Pochampally's credit notes reference a March/April
    invoice that was never in this tool's own records, and no GSTIN
    should ever be fabricated for a GST filing.
    """
    if not original_invoice_no:
        return None
    return lookup_fn(original_invoice_no)


def _try_vision_extraction(pdf_path, tenant_id):
    """
    Attempts direct vision extraction for a scanned/photographed PDF (see
    backend/vision_scan_extraction.py). Returns a populated
    InvoiceExtractionResponse on success, or None to fall through to the
    standard docling-based OCR pipeline -- no tenant GSTIN on file yet
    (vision needs it to tell buyer from vendor), vision found nothing
    usable, or the call failed for any reason.
    """
    try:
        from database import SessionLocal
        from models import Tenant
        db = SessionLocal()
        try:
            tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        finally:
            db.close()
        if not tenant or not tenant.gstin:
            return None

        from vision_scan_extraction import extract_scan_via_vision
        invoices = extract_scan_via_vision(pdf_path, tenant.name, tenant.gstin)
        if not invoices:
            return None

        all_res = InvoiceExtractionResponse()
        for inv in invoices:
            for item in inv.get("items", []):
                all_res.purchase_items.append(SuvitPurchaseItem(
                    voucher_date=inv.get("invoice_date"),
                    invoice_no=inv.get("invoice_no"),
                    party_ledger_name=inv.get("party_ledger_name"),
                    party_gstin=inv.get("party_gstin"),
                    place_of_supply=inv.get("place_of_supply"),
                    particulars=item.get("name_of_item"),
                    hsn=item.get("hsn"),
                    qty=item.get("quantity") or 0.0,
                    rate=item.get("rate") or 0.0,
                    taxable_value=item.get("amount") or 0.0,
                    cgst_amount=item.get("cgst") or 0.0,
                    sgst_amount=item.get("sgst") or 0.0,
                    igst_amount=item.get("igst") or 0.0,
                    total_invoice_value=item.get("total_amount") or 0.0,
                ))

        if not all_res.purchase_items:
            return None

        all_res.overall_taxable_value = sum(it.taxable_value for it in all_res.purchase_items)
        all_res.overall_cgst_amount = sum(it.cgst_amount for it in all_res.purchase_items)
        all_res.overall_sgst_amount = sum(it.sgst_amount for it in all_res.purchase_items)
        all_res.overall_igst_amount = sum(it.igst_amount for it in all_res.purchase_items)
        all_res.overall_total_invoice_value = sum(it.total_invoice_value for it in all_res.purchase_items)
        return all_res
    except Exception as e:
        print(f"  [VisionExtraction] Falling back to OCR pipeline: {e}")
        return None


def process_pdf(pdf_path, model_override=None, invoice_type="both", logger=None, tenant_id=None):
    import time
    from services.observability import now_utc

    # 1. File Intake Stage
    started_intake = now_utc()
    try:
        doc = fitz.open(pdf_path)
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

    # Scanned/photographed documents: try direct vision extraction first
    # (reads the image directly, no docling/OCR-text step) when this tenant
    # has a GSTIN on file to identify the buyer. Purchase-side only, matching
    # vision_extractor.py's existing usage. Falls through to the standard
    # docling-based pipeline below on any failure.
    if scan_type == "scanned_ocr" and tenant_id and invoice_type.lower() in ("purchase", "both"):
        vision_res = _try_vision_extraction(pdf_path, tenant_id)
        if vision_res is not None:
            doc.close()
            return vision_res

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

    # Targeted model escalation: invoices with discount/advance/late-fee rows
    # have non-standard column layouts (negative deduction rows, dual-meaning
    # columns) that gemini-2.5-flash has been confirmed (empirically, on real
    # invoices) to mis-extract even with explicit prompt rules in place.
    # Escalate just these to the Pro model rather than accepting silently
    # wrong numbers or blanket-upgrading every invoice's cost.
    _ESCALATION_KEYWORDS = ("discount", "advance paid", "late fee", "late payment", "penalty", "interest charge")
    if any(kw in full_text.lower() for kw in _ESCALATION_KEYWORDS):
        if model_name == "gemini-2.5-flash":
            print("  [ModelEscalation] Discount/advance/late-fee row detected — using gemini-2.5-pro for this invoice.")
            model_name = "gemini-2.5-pro"
        elif model_name == "google/gemini-2.5-flash":
            print("  [ModelEscalation] Discount/advance/late-fee row detected — using google/gemini-2.5-pro for this invoice.")
            model_name = "google/gemini-2.5-pro"

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

    # LLM extraction sometimes omits a tax field entirely (JSON null) rather
    # than writing 0 — e.g. an invoice with only IGST leaves cgst/sgst as
    # null. Pydantic's float fields reject None outright, so coerce before
    # constructing the model rather than losing the whole invoice to a
    # validation error over an absent-but-legitimately-zero field.
    _NUMERIC_ITEM_FIELDS = ("qty", "rate", "taxable_value", "cgst_amount",
                             "sgst_amount", "igst_amount", "total_invoice_value")

    def _coerce_numeric_nulls(item):
        for f in _NUMERIC_ITEM_FIELDS:
            if item.get(f) is None:
                item[f] = 0.0
        return item

    for item in raw_extracted.get("sales_items", []):
        all_res.sales_items.append(SuvitSalesItem(**_coerce_numeric_nulls(item)))
    for item in raw_extracted.get("purchase_items", []):
        all_res.purchase_items.append(SuvitPurchaseItem(**_coerce_numeric_nulls(item)))
        
    # ── Canonical financial values from Reconciliation Engine ────────────────
    # recon_report.canonical_values already picks, per field, whichever source
    # FIELD_SOURCE_AUTHORITY ranks strongest (line-item evidence for
    # taxable_value/grand_total, invoice-summary for cgst/sgst/igst) — see
    # core/reconciliation/canonical.py. Only fields marked "corrected" actually
    # differ from the LLM's own value, so this loop is a no-op for the rest.
    recon_report = bundle.__dict__.get("reconciliation")
    ground_truth_correction = {"applied": False}

    if recon_report:
        for canon_field, attr_name in _CANONICAL_TO_OVERALL_ATTR.items():
            entry = recon_report.canonical_values.get(canon_field)
            if entry and entry.get("corrected"):
                llm_value = getattr(all_res, attr_name)
                setattr(all_res, attr_name, entry["value"])
                ground_truth_correction[attr_name] = {
                    "llm_value": llm_value,
                    "document_value": entry["value"],
                    "source": entry.get("source"),
                }
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

    # ── Deterministic line-item breakdown (canonical, replaces LLM sales_items) ──
    # Breaks the invoice into its per-section billing lines (SaaS, Soundbox,
    # Transactional Messages, KYC, Late Fee, etc.) via regex instead of
    # whatever the LLM happened to extract as "sales_items". Only attempted
    # when the GST summary table itself parsed (gst_table non-empty) - that's
    # the deterministic invoice-level ground truth this needs to prorate tax
    # against, and its rates (cgst_rate/sgst_rate/igst_rate). Falls back to
    # the LLM's sales_items untouched if no section matched at all (not a
    # recognized OneStack template) - see extract_deterministic_line_items.
    used_deterministic_line_items = False
    if invoice_type in ("sales", "both") and gst_table:
        header = _extract_invoice_header(full_text)
        det_items = extract_deterministic_line_items(
            full_text, all_res.overall_taxable_value,
            gst_table.get('cgst_rate', 0.0), gst_table.get('sgst_rate', 0.0),
            gst_table.get('igst_rate', 0.0),
        )
        if det_items:
            all_res.sales_items = [
                SuvitSalesItem(
                    voucher_date=header.get("voucher_date"),
                    voucher_type="Sales",
                    invoice_no=header.get("invoice_no"),
                    party_ledger_name=header.get("party_name"),
                    party_gstin=header.get("party_gstin"),
                    place_of_supply=header.get("place_of_supply"),
                    particulars=it["particulars"],
                    hsn=it["hsn"],
                    taxable_value=it["taxable"],
                    cgst_amount=it["cgst"],
                    sgst_amount=it["sgst"],
                    igst_amount=it["igst"],
                    total_invoice_value=it["total"],
                )
                for it in det_items
            ]
            used_deterministic_line_items = True

    # Guard: if the printed GST summary table OR the LLM-extracted overall amounts show
    # non-zero taxes, the invoice is domestic — not export/LUT — regardless of any
    # text-based export phrase detection (which can false-positive on vendor/product names).
    _gst_table_taxes = (
        gst_table.get('cgst_amount', 0.0) +
        gst_table.get('sgst_amount', 0.0) +
        gst_table.get('igst_amount', 0.0)
    ) if gst_table else 0.0
    _overall_taxes = (
        (all_res.overall_cgst_amount or 0.0) +
        (all_res.overall_sgst_amount or 0.0) +
        (all_res.overall_igst_amount or 0.0)
    )
    if _gst_table_taxes > 0.0 or _overall_taxes > 0.0:
        _is_export_invoice = False

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
        "canonical_financial_values": ground_truth_correction,
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

    if used_deterministic_line_items:
        # Deterministic items are already reconciled to the invoice-level
        # ground truth by construction (advance cascade + tax proration
        # applied at extraction time, see extract_deterministic_line_items).
        # The LLM-noise-cleanup steps below (subtotal removal, taxable
        # correction, unallocated-variance injection, HSN-blank-autofill)
        # exist to fix problems that only arise from LLM extraction and
        # would only introduce risk here - HSN-autofill in particular would
        # incorrectly force "9971" onto sections that genuinely have no HSN
        # printed on the invoice (see NOT_SPECIFIED_HSN). Only classify
        # gstr1_category per item, which is safe and doesn't touch amounts.
        for item in all_res.sales_items:
            item.gstr1_category = classify_gstr1_item(item)
        if _is_export_invoice:
            for item in all_res.sales_items:
                item.cgst_amount = 0.0
                item.sgst_amount = 0.0
                item.igst_amount = 0.0
                item.total_invoice_value = round(item.taxable_value or 0.0, 2)
                item.gstr1_category = "EXPORT"
            all_res.overall_cgst_amount = 0.0
            all_res.overall_sgst_amount = 0.0
            all_res.overall_igst_amount = 0.0
            all_res.overall_total_invoice_value = all_res.overall_taxable_value

    elif all_res.sales_items:
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

        # Gap-fill missing line items (replaces old "Unallocated / Missing Lines"
        # fabrication). If the LLM's line items don't sum to the invoice's own
        # total, we used to inject a synthetic placeholder row with a made-up
        # HSN and no real particulars — that's fabricated data, and it has been
        # observed to inject amounts (e.g. ~₹2 lakh on a real client invoice)
        # that don't correspond to anything on the actual document. Instead,
        # make one targeted follow-up call asking specifically for the missing
        # item(s), grounded in the invoice text. If that genuinely can't find
        # anything, leave the gap as-is — the reconciliation engine will
        # correctly flag the invoice as BLOCKED/NEEDS_REVIEW for human review,
        # which is the honest outcome, not a plugged number.
        # Compare on the SAME anchor the reconciliation engine actually checks
        # (taxable value only, not tax-inclusive total) — using a different
        # anchor here than the engine uses downstream meant this block could
        # see no variance while the engine still blocked the invoice (or vice
        # versa). Line items are gross (pre-advance); when the invoice deducts
        # an advance payment before computing GST, overall_taxable_value is
        # already net-of-advance, so add the advance back to get the gross
        # target line items should actually sum to.
        _sum_taxable = sum(item.taxable_value or 0.0 for item in cleaned_sales)
        _expected_taxable = (all_res.overall_taxable_value or 0.0) + (all_res.overall_advance_amount or 0.0)
        diff = _expected_taxable - _sum_taxable

        # Skip phantom injection when diff ≈ tax on existing items (items extracted without per-line taxes)
        _diff_is_just_tax = any(abs(diff - _sum_taxable * r) < 5.0 for r in (0.18, 0.12, 0.05, 0.28))

        if _expected_taxable > 0 and diff > 1.0 and not _diff_is_just_tax:
            found_items = _fill_missing_sales_line_items(
                full_text=full_text,
                existing_items=cleaned_sales,
                variance_amount=diff,
                client=client,
                model_name=model_name,
            )
            if found_items:
                cleaned_sales.extend(found_items)
                correction_meta["gap_fill_rows_found"] = len(found_items)
                correction_meta["gap_fill_details"] = {
                    "variance_amount": diff,
                    "particulars": [it.particulars for it in found_items],
                }
            else:
                correction_meta["gap_fill_rows_found"] = 0
                correction_meta["unresolved_variance"] = diff

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

    # A 15-char string isn't proof of a real, active registration -- verify
    # against the GST registry (cached) and auto-correct has_gstin when we
    # get a confident answer. Best-effort: any failure keeps the length-only
    # heuristic above rather than blocking classification.
    gstin_verified_status = None
    if has_gstin:
        try:
            from database import SessionLocal
            from services.gstin_verification import get_gstin_info, resolve_b2b_status
            db = SessionLocal()
            try:
                info = get_gstin_info(gstin, db)
            finally:
                db.close()
            if info and info.get("status"):
                gstin_verified_status = info["status"]
                # AS OF the invoice date, not today's live status -- a
                # registration suspended/cancelled after this invoice was
                # raised still counts as B2B. "needs_review" (status
                # changed but the timing can't be determined) deliberately
                # leaves has_gstin unchanged rather than guessing B2C --
                # RuleGST005 surfaces that case for a human to confirm.
                b2b_status = resolve_b2b_status(info, str(item.voucher_date or ""))
                if b2b_status == "inactive":
                    has_gstin = False
        except Exception:
            pass  # verification is a bonus, never a hard dependency

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
        # Signal: total_invoice_value ≈ taxable_value (no tax baked in yet).
        # Use <= so 100%-discount cases (discount == amount) are also corrected.
        if qty == 0 and rate == 0 and discount <= taxable:
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
        
        # NOTE: this used to inject a fabricated "Unallocated / Missing Lines" placeholder row
        # here (guessed taxable value, 18%-split tax) whenever line items didn't sum to
        # extraction_response.overall_total_invoice_value. That fabrication was removed from
        # process_pdf's code path this session (replaced with an honest gap-fill-or-leave-for-review
        # mechanism) because it was observed injecting amounts that don't correspond to anything on
        # the real invoice. Removed here too for the same reason — do not re-add it. This function
        # only ever receives an already-aggregated, multi-invoice extraction_response (see its only
        # caller, main.py's /api/export/{batch_id}) with overall_total_invoice_value never populated,
        # so there's nothing meaningful to gap-fill against at this level anyway; genuine per-invoice
        # gaps are already surfaced upstream via recon_status during extraction.

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
