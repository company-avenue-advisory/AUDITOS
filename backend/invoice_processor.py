import os
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
    overall_total_invoice_value: float = Field(0.0, description="Overall Total Invoice Value incl taxes")
    sales_items: List[SuvitSalesItem] = Field(default_factory=list, description="Extracted sales items")
    purchase_items: List[SuvitPurchaseItem] = Field(default_factory=list, description="Extracted purchase items")

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
    schema_json = InvoiceExtractionResponse.model_json_schema()
    
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
    for attempt in range(max_retries):
        try:
            print(f"  Analyzing content (attempt {attempt+1})...")
            
            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": messages_content}],
                response_format={"type": "json_object"},
                temperature=0.0
            )
            
            content = response.choices[0].message.content.strip()
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                content = json_match.group(0)
                
            import json
            data = InvoiceExtractionResponse(**json.loads(content))
            return data
            
        except Exception as e:
            if attempt == max_retries - 1:
                raise e
            time.sleep(10 * (attempt + 1) if "429" in str(e) or "503" in str(e) else 2)

def process_pdf(pdf_path, model_override=None, invoice_type="both"):
    import pdfplumber
    try:
        doc = fitz.open(pdf_path)
        pdf_plumber_doc = pdfplumber.open(pdf_path)
        total_pages = len(doc)
    except Exception as e:
        print(f"  Error opening PDF {pdf_path}: {e}")
        return InvoiceExtractionResponse()
        
    if total_pages == 0:
        return InvoiceExtractionResponse()

    is_cloud_primary = False
    if model_override and model_override.get("provider") == "openrouter":
        model_name = model_override["model"]
        base_url = "https://openrouter.ai/api/v1"
        api_key = os.getenv("OPENROUTER_API_KEY", "dummy")
        is_cloud_primary = True
    elif model_override and model_override.get("provider") == "ollama":
        model_name = model_override.get("model") or os.getenv("OLLAMA_MODEL_NAME", "qwen2.5:7b")
        base_url = os.getenv("OLLAMA_API_BASE", "http://localhost:11434/v1")
        api_key = os.getenv("OLLAMA_API_KEY", "ollama")
    else:
        # 🚀 Google Gemini Direct API Integration
        model_name = "gemini-2.5-flash"
        base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
        api_key = os.getenv("GEMINI_API_KEY", "")
        is_cloud_primary = True
        
    from openai import OpenAI
    client = OpenAI(api_key=api_key, base_url=base_url)
    
    CHUNK_SIZE = 3
    OVERLAP = 1
    
    all_res = InvoiceExtractionResponse()
    
    if total_pages <= CHUNK_SIZE:
        pdf_contents = []
        has_content = False
        for page in doc:
            content_item = extract_page_content(page, pdf_plumber_doc.pages[page.number])
            pdf_contents.append(content_item)
            if content_item["content"]:
                has_content = True
        if has_content:
            res = call_llm(pdf_contents, model_name, client, invoice_type)
            if res:
                all_res.sales_items.extend(res.sales_items)
                all_res.purchase_items.extend(res.purchase_items)
                if res.overall_taxable_value > 0:
                    all_res.overall_taxable_value = res.overall_taxable_value
                    all_res.overall_cgst_amount = res.overall_cgst_amount
                    all_res.overall_sgst_amount = res.overall_sgst_amount
                    all_res.overall_igst_amount = res.overall_igst_amount
                    all_res.overall_total_invoice_value = res.overall_total_invoice_value
    else:
        start = 0
        while start < total_pages:
            end = min(start + CHUNK_SIZE, total_pages)
            chunk_contents = []
            has_content = False
            for p_num in range(start, end):
                content_item = extract_page_content(doc[p_num], pdf_plumber_doc.pages[p_num])
                chunk_contents.append(content_item)
                if content_item["content"]:
                    has_content = True
                
            if has_content:
                res = call_llm(chunk_contents, model_name, client, invoice_type)
                if res:
                    all_res.sales_items.extend(res.sales_items)
                    all_res.purchase_items.extend(res.purchase_items)
                    if res.overall_taxable_value > 0:
                        all_res.overall_taxable_value = res.overall_taxable_value
                        all_res.overall_cgst_amount = res.overall_cgst_amount
                        all_res.overall_sgst_amount = res.overall_sgst_amount
                        all_res.overall_igst_amount = res.overall_igst_amount
                        all_res.overall_total_invoice_value = res.overall_total_invoice_value
            if end == total_pages:
                break
            start += CHUNK_SIZE - OVERLAP
            
    # CA-level strict regex fallback for totals
    import re
    full_text = ""
    for page in doc:
        full_text += page.get_text() + "\n"
        
    if all_res.overall_taxable_value == 0:
        net_cost_match = re.search(r'Final Total \([^)]+\)\n([0-9,.]+)', full_text) or re.search(r'Net Cost\n([0-9,.]+)', full_text)
        if net_cost_match:
            all_res.overall_taxable_value = float(net_cost_match.group(1).replace(',', ''))
            
        cgst_match = re.search(r'CGST @[0-9.%]*\n([0-9,.]+)', full_text)
        if cgst_match:
            all_res.overall_cgst_amount = float(cgst_match.group(1).replace(',', ''))
            
        sgst_match = re.search(r'SGST @[0-9.%]*\n([0-9,.]+)', full_text)
        if sgst_match:
            all_res.overall_sgst_amount = float(sgst_match.group(1).replace(',', ''))
            
        total_match = re.search(r'Total Cost incl Taxes\n([0-9,.]+)', full_text)
        if total_match:
            all_res.overall_total_invoice_value = float(total_match.group(1).replace(',', ''))
            
    return all_res

def deduplicate_sales(df):
    if df.empty: return df
    # Removed aggressive deduplication to avoid dropping line items with the same tax rate/amount
    return df.drop_duplicates()

def deduplicate_purchase(df):
    if df.empty: return df
    df = df.drop_duplicates(subset=["Invoice No", "Party Ledger Name", "Item/Ledger Name", "Taxable Value"], keep="first")
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
        if not item.hsn or str(item.hsn).lower() in ["nan", "none", ""]:
            desc = str(item.particulars).lower()
            assigned = False
            for key, hsn in hsn_map.items():
                if key in desc:
                    item.hsn = hsn
                    assigned = True
                    break
            if not assigned:
                item.hsn = "9971"
        valid_items.append(item)
    return valid_items

def math_verification_agent(sales_items):
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
        
        # If the LLM completely hallucinated 0 tax but the HSN is a services HSN (99xx), force 18%
        if snapped_rate == 0.0 and str(item.hsn).startswith("99"):
            snapped_rate = 0.18
            
        is_interstate = igst_extracted > (cgst_extracted + sgst_extracted)
        
        if is_interstate:
            item.igst_amount = round(taxable * snapped_rate, 2)
            item.cgst_amount = 0.0
            item.sgst_amount = 0.0
        else:
            item.igst_amount = 0.0
            item.cgst_amount = round(taxable * (snapped_rate / 2), 2)
            item.sgst_amount = round(taxable * (snapped_rate / 2), 2)
            
        item.total_invoice_value = round(taxable + item.igst_amount + item.cgst_amount + item.sgst_amount, 2)
    return sales_items

def build_dataframes(extraction_response):
    sales_dfs = {"Main": pd.DataFrame(), "Narration": pd.DataFrame(), "LineItems": pd.DataFrame()}
    if extraction_response.sales_items:
        # Prevent double counting by removing sub-totals
        extraction_response.sales_items = remove_subtotals(extraction_response.sales_items)
        
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
        extraction_response.sales_items = math_verification_agent(extraction_response.sales_items)
        
        
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
                "HSN": item.hsn
            })
        df_all = pd.DataFrame(records)
        df_all = deduplicate_sales(df_all)
        
        # 1. Main Sheet (Strictly ONE row per invoice)
        group_cols = ["REFERANCE NO", "INVOICE DATE", "GST NO", "PARTY A/C NAME", "PLACE OF SUPPLY"]
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
            
        hsn_vals = df_all.groupby(group_cols, dropna=False)["HSN"].apply(get_single_hsn).reset_index()
        narr_vals = df_all.groupby(group_cols, dropna=False)["Narration"].first().reset_index()
        
        df_main = df_main.merge(hsn_vals, on=group_cols, how="left")
        df_main = df_main.merge(narr_vals, on=group_cols, how="left")
        
        main_cols = ["REFERANCE NO", "INVOICE DATE", "GST NO", "PARTY A/C NAME", "PLACE OF SUPPLY", "PARTICULARS", "AMOUNT", "DISCOUNT", "ADVANCES", "SGST", "CGST", "IGST", "TOTAL AMOUNT", "Narration", "HSN"]
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
                "Voucher Date": item.voucher_date,
                "Voucher Type": item.voucher_type,
                "Invoice No": item.invoice_no,
                "Party Ledger Name": item.party_ledger_name,
                "Party GSTIN": item.party_gstin,
                "Place of Supply": item.place_of_supply,
                "Item/Ledger Name": item.particulars,
                "HSN": item.hsn,
                "Qty": item.qty,
                "Rate": item.rate,
                "Taxable Value": item.taxable_value,
                "CGST Amount": item.cgst_amount,
                "SGST Amount": item.sgst_amount,
                "IGST Amount": item.igst_amount,
                "Total Invoice Value": item.total_invoice_value,
                "ITC Category": item.itc_category,
                "Narration": item.narration
            })
        purchase_df = pd.DataFrame(records)
        purchase_df = deduplicate_purchase(purchase_df)
        
    return sales_dfs, purchase_df
