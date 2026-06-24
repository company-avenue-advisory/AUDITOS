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

load_dotenv()

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
    text = ""
    try:
        with fitz.open(pdf_path) as doc:
            for page in doc:
                text += page.get_text() + "\n"
    except Exception as e:
        print(f"  Error extracting text from PDF {pdf_path}: {e}")
    return text

def extract_page_text_with_ocr_fallback(page, client):
    text = page.get_text()
    if len(text.strip()) < 50:
        try:
            pix = page.get_pixmap()
            img_data = pix.tobytes("png")
            base64_image = base64.b64encode(img_data).decode('utf-8')
            
            from openai import OpenAI
            openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
            if not openrouter_api_key:
                return text + "\n"
            openrouter_client = OpenAI(api_key=openrouter_api_key, base_url="https://openrouter.ai/api/v1")
            
            response = openrouter_client.chat.completions.create(
                model="google/gemini-2.5-flash",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Perform high-fidelity OCR on this invoice page."},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
                        ]
                    }
                ],
                temperature=0.0
            )
            return response.choices[0].message.content + "\n"
        except Exception:
            return text + "\n"
    return text + "\n"

def call_llm_for_text(pdf_text, model_name, client, invoice_type="both"):
    schema_json = InvoiceExtractionResponse.model_json_schema()
    
    prompt = f"""
Role: You are the core processing engine for "Audit OS," an advanced tax and compliance automation platform used by Chartered Accountants in India.

Objective: Extract structured data from raw, messy PDF text streams and automatically route them into strict, compliant data schemas (Suvit/Tally Excel templates) based on the current Indian GST and Income Tax laws.

Part 1: Operating Principles
- Be Specific: Extract specifically requested fields mapped to statutory naming conventions.
- Context is King: Assume amounts are in INR. Dates are DD-MMM-YYYY. GSTIN is a 15-character string.
- Formatting: For ALL numeric amounts, output plain floats WITHOUT commas (e.g., 29784.58 instead of 29,784.58).
- Handle Edge Cases Gracefully: Leave missing fields null/empty.
- Follow the Routing Rules Absolutely: Accurately determine the document's category based on logic rules.
- Narration Field: This is ONLY for genuine CA warnings (e.g. 'TDS 2% liable to be deducted') or actual invoice notes. DO NOT output internal logic rules (like 'No buyer_gstin...') here. Leave blank if no genuine note exists.

Part 2: The Core Routing Engines
You are currently operating in "{invoice_type}" mode.

Engine A: Sales & GSTR-1 (Outward Supplies)
Input: Raw text from a Sales Invoice issued by the user's client.
1. Extraction Requirements: Invoice Date, Invoice Number, Buyer Name, Buyer GSTIN, Place of Supply, Line Items (Item description, HSN code, Quantity, Rate), Taxable Value, Discounts, Advances, Tax Amounts, Total Invoice Value. Also extract the Overall Invoice Totals (overall_taxable_value, overall_cgst_amount, etc.) exactly as stated at the bottom of the invoice.
2. GSTR-1 Categorization Logic:
- Table 4 (B2B): buyer_gstin is present and valid (15 chars).
- Table 5 (B2CL): No buyer_gstin AND place_of_supply != seller_state AND total_invoice_value > 100000.
- Table 7 (B2CS): No buyer_gstin AND (place_of_supply == seller_state OR total_invoice_value <= 100000).
- Table 9B (CDNR): Document type is "Credit Note" or "Debit Note" AND buyer_gstin is present.
- Table 14/15 (ECO): Buyer is an E-Commerce Operator liable under Sec 9(5) or Sec 52.
3. Compliance Guardrails:
- CRITICAL: You MUST extract EVERY distinct line item from the invoice exactly as it appears. Do NOT skip any items. Do NOT summarize or group items. 
- CA GUARDRAILS for Amount: Do NOT accidentally extract HSN codes (e.g., 5540.00, 9971) or reference values as the 'taxable_value'! The taxable value is usually the last column. If an item has a discount, ensure 'taxable_value' is the NET amount (Gross - Discount).
- CA GUARDRAILS for Description: For 'particulars', use the actual granular description (e.g. 'SMS Login', 'SMS Transactions', 'App Notifications', 'Late Fees'). Do NOT just use the generic section header (like 'D Transactional Messages') for all items.
- The sum of ALL extracted line item `taxable_value` amounts MUST EXACTLY EQUAL the invoice's Final Taxable Value (e.g., Sub Total before taxes).
- If per-item tax is not explicitly stated on the invoice, apportion the overall total invoice taxes (CGST, SGST, IGST) proportionally to each line item based on its taxable value. The sum of all line item taxes must exactly equal the total tax on the invoice.
- Any rounding off amounts should be absorbed into the total. Extract discounts and advances per line item if available.

Engine B: Purchase & GSTR-2B (Inward Supplies & ITC)
Input: Raw text from a Purchase Invoice received by the user's client from a vendor.
1. Extraction Requirements: Invoice Date, Invoice Number, Supplier Name, Supplier GSTIN, Place of Supply, Items/Description, HSN, Taxable Value, CGST, SGST, IGST, Total Value.
2. ITC Routing Logic:
- Eligible ITC: Standard business purchases with valid GST.
- Blocked ITC (Sec 17(5)): Flag "Motor Vehicles", "Food & Beverages", "Club Memberships", "Life Insurance", "Personal Consumption". Route to Ineligible ITC.
- RCM: Flag services like "GTA", "Legal Fees", "Sponsorship". Route to RCM tables.
- Import of Goods/Services: Identify "Bill of Entry" or foreign currency.
- Exempt/Nil Rated: Identify 0% tax rate items.
3. Compliance Guardrails:
- TDS Check (Sec 194C/J): Calculate if TDS should have been deducted (e.g., Professional fees > 30000). Flag if missing in Narration.

Part 3: Execution Instruction
If mode is "both", first auto-classify the document:
- If titled "Tax Invoice" and client's GSTIN matches Supplier GSTIN -> Classify as Sales.
- If bill/invoice from a vendor, and client's GSTIN matches Buyer GSTIN -> Classify as Purchase.
(Note: Our client is usually OneStack / One Stack Solution Private Limited).

Output the final result as a JSON object matching this schema:
{schema_json}

===== TEXT CONTENT OF PDF INVOICE =====
{pdf_text}
"""
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            print(f"  Analyzing text (attempt {attempt+1})...")
            try:
                response = client.beta.chat.completions.parse(
                    model=model_name,
                    messages=[{"role": "user", "content": prompt}],
                    response_format=InvoiceExtractionResponse,
                    temperature=0.0
                )
                if response.choices[0].message.parsed:
                    return response.choices[0].message.parsed
            except Exception as parse_err:
                print(f"  Structured parsing failed ({parse_err}). Trying JSON mode...")
            
            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
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
    try:
        doc = fitz.open(pdf_path)
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
        if total_pages <= 5:
            model_name = "meta-llama/llama-3.3-70b-instruct"
            base_url = "https://openrouter.ai/api/v1"
            api_key = os.getenv("OPENROUTER_API_KEY", "dummy")
            is_cloud_primary = True
        else:
            model_name = os.getenv("OLLAMA_MODEL_NAME", "qwen2.5:7b")
            base_url = os.getenv("OLLAMA_API_BASE", "http://localhost:11434/v1")
            api_key = os.getenv("OLLAMA_API_KEY", "ollama")
        
    from openai import OpenAI
    client = OpenAI(api_key=api_key, base_url=base_url)
    
    CHUNK_SIZE = 3
    OVERLAP = 1
    
    all_res = InvoiceExtractionResponse()
    
    if total_pages <= CHUNK_SIZE:
        pdf_text = ""
        for page in doc:
            pdf_text += extract_page_text_with_ocr_fallback(page, client)
        if pdf_text.strip():
            res = call_llm_for_text(pdf_text, model_name, client, invoice_type)
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
            chunk_text = ""
            for p_num in range(start, end):
                chunk_text += extract_page_text_with_ocr_fallback(doc[p_num], client)
                
            if chunk_text.strip():
                res = call_llm_for_text(chunk_text, model_name, client, invoice_type)
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

def build_dataframes(extraction_response):
    sales_dfs = {"Main": pd.DataFrame(), "Narration": pd.DataFrame(), "LineItems": pd.DataFrame()}
    if extraction_response.sales_items:
        # Prevent double counting by removing sub-totals
        extraction_response.sales_items = remove_subtotals(extraction_response.sales_items)
        
        # --- Mathematical Balancing Logic ---
        overall_taxable = extraction_response.overall_taxable_value
        overall_cgst = extraction_response.overall_cgst_amount
        overall_sgst = extraction_response.overall_sgst_amount
        overall_igst = extraction_response.overall_igst_amount
        overall_total = extraction_response.overall_total_invoice_value

        # Guardrail: Fix Gross vs Net hallucination dynamically
        for item in extraction_response.sales_items:
            if (item.discount or 0.0) > 0 and (item.taxable_value or 0.0) > 0:
                current_sum = sum(x.taxable_value or 0.0 for x in extraction_response.sales_items)
                if abs((current_sum - item.discount) - overall_taxable) < abs(current_sum - overall_taxable):
                    item.taxable_value = round(item.taxable_value - item.discount, 2)

        sum_taxable = sum(item.taxable_value or 0.0 for item in extraction_response.sales_items)
        diff = overall_taxable - sum_taxable
        
        # If there's a discrepancy (under-extracted), add a missing line item
        if sum_taxable > 0 and overall_taxable > 0 and diff > 1.0:
            dummy_item = SuvitSalesItem(
                voucher_date=extraction_response.sales_items[0].voucher_date,
                invoice_no=extraction_response.sales_items[0].invoice_no,
                party_gstin=extraction_response.sales_items[0].party_gstin,
                party_ledger_name=extraction_response.sales_items[0].party_ledger_name,
                place_of_supply=extraction_response.sales_items[0].place_of_supply,
                particulars="Unallocated / Missing Lines",
                taxable_value=diff,
                cgst_amount=round((diff / overall_taxable) * overall_cgst, 2),
                sgst_amount=round((diff / overall_taxable) * overall_sgst, 2),
                igst_amount=round((diff / overall_taxable) * overall_igst, 2)
            )
            extraction_response.sales_items.append(dummy_item)
            sum_taxable += diff

        # Re-calculate taxes (and clamp over-extracted amounts) proportionally
        if sum_taxable > 0 and overall_taxable > 0:
            for item in extraction_response.sales_items:
                proportion = (item.taxable_value or 0.0) / sum_taxable
                item.cgst_amount = round(overall_cgst * proportion, 2)
                item.sgst_amount = round(overall_sgst * proportion, 2)
                item.igst_amount = round(overall_igst * proportion, 2)
                
                # Guardrail: If AI over-extracted, scale the taxable value down proportionally
                if diff < -1.0:
                    item.taxable_value = round(overall_taxable * proportion, 2)
                    
                item.total_invoice_value = item.taxable_value + item.cgst_amount + item.sgst_amount + item.igst_amount
        else:
            # Fallback if overall totals weren't extracted properly by LLM
            # Fix hallucinated totals
            for item in extraction_response.sales_items:
                item.total_invoice_value = (item.taxable_value or 0.0) + (item.cgst_amount or 0.0) + (item.sgst_amount or 0.0) + (item.igst_amount or 0.0)

        # --- End Balancing ---
        
        records = []
        for item in extraction_response.sales_items:
            tax = (item.cgst_amount or 0) + (item.sgst_amount or 0) + (item.igst_amount or 0)
            taxable = item.taxable_value or 0
            rate = round((tax / taxable) * 100) if taxable > 0 else 0
            particulars_val = f"Sales IGST {rate}" if (item.igst_amount or 0) > 0 else f"Sales GST {rate}"
            
            records.append({
                "REFERANCE NO": item.invoice_no,
                "INVOICE DATE": item.voucher_date,
                "GST NO": item.party_gstin,
                "PARTY A/C NAME": item.party_ledger_name,
                "PLACE OF SUPPLY": item.place_of_supply,
                "RAW_PARTICULARS": item.particulars,
                "GROUP_PARTICULARS": particulars_val,
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
        
        # 1. Main Sheet (Subtotals)
        group_cols = ["REFERANCE NO", "INVOICE DATE", "GST NO", "PARTY A/C NAME", "PLACE OF SUPPLY", "GROUP_PARTICULARS"]
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
        # Add Narration and HSN (first per group)
        first_vals = df_all.groupby(group_cols, dropna=False)[["Narration", "HSN"]].first().reset_index()
        df_main = df_main.merge(first_vals, on=group_cols, how="left")
        df_main.rename(columns={"GROUP_PARTICULARS": "PARTICULARS"}, inplace=True)
        
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
        df_line.drop(columns=["GROUP_PARTICULARS"], inplace=True)
        
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
