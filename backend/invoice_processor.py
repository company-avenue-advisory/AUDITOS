import os
import argparse
import fitz  # PyMuPDF
import pandas as pd
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from dotenv import load_dotenv
import re
import tempfile
import time
import base64

load_dotenv()

class LineItem(BaseModel):
    supplier_inv: Optional[str] = Field(default=None, description="SUPPLIER INV: The exact invoice number as printed on the invoice. Must be the full alphanumeric string.")
    invoice_date: Optional[str] = Field(default=None, description="INVOICE DATE: In DD-MMM-YYYY format (e.g. 12-Jun-2026). Extract the exact date printed on the invoice.")
    gst_no: Optional[str] = Field(default=None, description="GST NO: The full 15-character Indian GSTIN of the supplier (e.g. 06AAACB2894P1Z5). Extract all 15 characters.")
    party_ac_name: Optional[str] = Field(default=None, description="PARTY A/C NAME: The FULL LEGAL registered company name of the supplier exactly as it appears on the invoice header. E.g. 'Bharti Airtel Limited', 'One Stack Solution Private Limited'. Never abbreviate or truncate.")
    place_of_supply: Optional[str] = Field(default=None, description="PLACE OF SUPPLY: State name (e.g. Haryana, Maharashtra)")
    particulars: Optional[str] = Field(default=None, description="PARTICULARS: The line item description or service name")
    amount: Optional[float] = Field(default=0.0, description="AMOUNT: The base taxable amount before taxes (NOT the total)")
    sgst: Optional[float] = Field(default=0.0, description="SGST amount")
    cgst: Optional[float] = Field(default=0.0, description="CGST amount")
    igst: Optional[float] = Field(default=0.0, description="IGST amount")
    total_amount: Optional[float] = Field(default=0.0, description="TOTAL AMOUNT: Final payable amount including all taxes")
    narration: Optional[str] = Field(default=None, description="Narration or payment terms noted on invoice")
    hsn: Optional[str] = Field(default=None, description="HSN: The HSN/SAC code (4, 6, or 8 digit numeric code)")

    @field_validator('gst_no')
    def validate_gst(cls, v):
        if not v:
            return v
        v = v.strip()
        # Indian GSTIN must be exactly 15 characters
        if len(v) != 15:
            if len(v) < 10:
                return None
        # Reject OneStack's own GSTIN (since we only want supplier GSTIN)
        onestack_gst = ['27aadco0061h1zq', '27aadc0061h1zq']
        if v.lower().strip() in onestack_gst:
            return None
        return v

    @field_validator('supplier_inv')
    def validate_inv(cls, v):
        if not v:
            return v
        v = str(v).strip()
        # Reject standalone 1-3 digit numbers (likely page numbers or serial numbers, not invoice IDs)
        if v.isdigit() and len(v) <= 3:
            return None
        return v

    @field_validator('party_ac_name')
    def validate_party_name(cls, v):
        if not v:
            return v
        v = v.strip()
        # Reject generic/garbage names
        garbage_names = ['tax invoice', 'invoice', 'page', 'bill', 'receipt', 'gst']
        if v.lower() in garbage_names:
            return None
        # OneStack is OUR company (the buyer), never the supplier
        onestack_variations = ['onestack', 'one stack', 'onestack solution', 'one stack solution',
                               'onestack solution private limited', 'one stack solution private limited',
                               'one stack solution pvt ltd', 'onestack solution pvt ltd',
                               'one stack solution pvt. ltd.', 'onestack solution pvt. ltd.']
        if v.lower().strip() in onestack_variations:
            return None
        return v

class InvoiceData(BaseModel):
    items: List[LineItem] = Field(default_factory=list, description="List of valid line items")

def extract_text_from_pdf(pdf_path):
    """Extract text content from all pages of the PDF using PyMuPDF (fitz)."""
    text = ""
    try:
        with fitz.open(pdf_path) as doc:
            for page in doc:
                text += page.get_text() + "\n"
    except Exception as e:
        print(f"  Error extracting text from PDF {pdf_path}: {e}")
    return text

def call_llm_for_text(pdf_text, model_name, client):
    """Sends extracted text block to the LLM and returns the list of LineItem objects."""
    schema_json = InvoiceData.model_json_schema()
    
    prompt = f"""
    You are an expert Indian auditor and strict invoice data extractor.
    
    TASK: Extract each UNIQUE invoice's data (including Tax Invoices, Demand Notes, Debit Notes, Bills, and payment requests) from the text below into structured LineItems.
    Return a single JSON object matching this JSON schema:
    {schema_json}
    
    ===== CRITICAL CONTEXT =====
    These invoices are received by "One Stack Solution Private Limited" (also known as "OneStack", "One Stack", "ONESTACK SOLUTION"). 
    OneStack is the BUYER / RECIPIENT. They are NOT the supplier.
    
    PARTY A/C NAME must ALWAYS be the SUPPLIER / VENDOR who ISSUED the invoice TO OneStack.
    - Look for the company name in the "From", "Billed By", "Seller", or the letterhead at the top.
    - NEVER put "OneStack", "One Stack Solution", or any variation as PARTY A/C NAME.
    - If you see "Billed To: One Stack Solution" — that confirms OneStack is the buyer. The OTHER company on the invoice is the supplier.
    
    ===== STRICT EXTRACTION RULES =====
    
    PARTY A/C NAME (CRITICAL):
    - Extract the FULL LEGAL registered company name of the SUPPLIER/VENDOR.
    - Examples: "Bharti Airtel Limited" (NOT "airtel"), "Awfis Space Solutions Private Limited" (NOT "Awfis").
    - NEVER abbreviate or truncate the company name.
    
    SUPPLIER INV (CRITICAL):
    - Extract the COMPLETE invoice number as printed. Include all prefixes, slashes, and suffixes.
    - Examples: "MF270610", "BAA062705B001987", "1-4671642"
    
    GST NO (CRITICAL):
    - Must be the FULL 15-character GSTIN of the SUPPLIER (not of OneStack).
    - Format: 2-digit state code + 10-char PAN + 1 entity code + 1Z + 1 checksum
    - Example: "06AAACB2894P1Z5" (exactly 15 chars)
    
    INVOICE DATE:
    - Format as DD-MMM-YYYY (e.g., "10-Jun-2026", "07-May-2026")
    
    DEDUPLICATION (CRITICAL):
    - If one invoice has a SUMMARY line (e.g., "Current Charges" or "Grand Total") AND also individual breakdown lines (e.g., "Rentals", "Usage"), extract ONLY the individual breakdown lines, NOT the summary.
    - Do not extract the same monetary amount twice for the same invoice IF one of them is a summary or subtotal line. However, if there are multiple legitimate separate detailed line items that happen to have the same amount (e.g., two different professional services both costing 40,000), you MUST extract each of them as separate line items.
    
    ZERO-VALUE LINES:
    - If a line item has Amount = 0 AND Total Amount = 0, SKIP it entirely.
    
    AMOUNTS (CRITICAL):
    - AMOUNT = base taxable amount (before tax)
    - TOTAL AMOUNT = Amount + SGST + CGST + IGST
    - All monetary values (AMOUNT, SGST, CGST, IGST, TOTAL AMOUNT) in the JSON MUST be parsed as plain numbers (floats/integers). Never output mathematical formulas or expressions (like "10000.0 - 2342.25" or "1038.0 + 1863.64") as values. Resolve all formulas to a single number before outputting.
    
    HSN / SAC (CRITICAL):
    - Extract the HSN/SAC code (typically a 4, 6, or 8 digit numeric code like 998311, 998319, 997212).
    - If a single HSN or SAC code is printed globally on the invoice (e.g. under bank details, centre information, general terms, or invoice summary) and not next to each individual line item, you MUST populate that same HSN/SAC code for ALL line items extracted from that invoice. Do not leave it empty.
    
    PREVENT FIELD MIX-UPS (CRITICAL):
    - If the text block contains text from multiple different invoices (e.g. different suppliers, different invoice numbers, or different dates), you MUST extract the correct `supplier_inv`, `invoice_date`, `gst_no`, and `party_ac_name` for each specific line item based on the invoice it belongs to.
    - NEVER mix headers. Do not assign the invoice number, date, GST, or supplier name of one invoice to the line items of another invoice. Keep each line item's metadata strictly associated with its own parent invoice.
    
    ===== TEXT CONTENT OF PDF INVOICE =====
    {pdf_text}
    """
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            print(f"  Analyzing text (attempt {attempt+1})...")
            # Try structured outputs using beta client first
            try:
                response = client.beta.chat.completions.parse(
                    model=model_name,
                    messages=[
                        {"role": "user", "content": prompt}
                    ],
                    response_format=InvoiceData,
                    temperature=0.0
                )
                if response.choices[0].message.parsed:
                    items = response.choices[0].message.parsed.items
                    print(f"  Extracted {len(items)} line items using structured parse.")
                    return items
            except Exception as parse_err:
                print(f"  Structured parsing failed or not supported ({parse_err}). Trying standard JSON mode...")
            
            # Fallback to standard chat completions with JSON mode
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.0
            )
            
            content = response.choices[0].message.content
            
            # Clean up content using regex to pull out the main JSON block if LLM added formatting
            content_cleaned = content.strip()
            json_match = re.search(r'\{.*\}', content_cleaned, re.DOTALL)
            if json_match:
                content_cleaned = json_match.group(0)
                
            import json
            data = InvoiceData(**json.loads(content_cleaned))
            print(f"  Extracted {len(data.items)} line items using JSON mode.")
            return data.items
            
        except Exception as e:
            err_str = str(e)
            print(f"  Error on attempt {attempt+1}: {e}")
            if attempt == max_retries - 1:
                # Raise the error on the final attempt to trigger fallback
                raise e
            if "429" in err_str or "503" in err_str:
                sleep_time = 10 * (attempt + 1)
                print(f"  Rate limit or temporary error. Waiting {sleep_time}s...")
                time.sleep(sleep_time)
            else:
                time.sleep(2)

def extract_page_text_with_ocr_fallback(page, client):
    """Extracts text from a single PDF page. If the page is empty/scanned, uses Groq vision OCR fallback."""
    text = page.get_text()
    if len(text.strip()) < 50:
        print(f"  Low/empty text detected on Page {page.number + 1} ({len(text.strip())} chars). Performing vision OCR fallback...")
        try:
            pix = page.get_pixmap()
            img_data = pix.tobytes("png")
            base64_image = base64.b64encode(img_data).decode('utf-8')
            
            # Instantiate a dedicated OpenRouter client for OCR fallback
            from openai import OpenAI
            openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
            if not openrouter_api_key:
                raise ValueError("OPENROUTER_API_KEY is not set in .env — cannot perform OCR fallback.")
            openrouter_client = OpenAI(api_key=openrouter_api_key, base_url="https://openrouter.ai/api/v1")
            
            # Use OpenRouter's vision model
            response = openrouter_client.chat.completions.create(
                model="google/gemini-2.5-flash",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Perform high-fidelity OCR on this invoice page. Extract ALL text, numbers, codes, and values. Pay close attention to tabular columns (such as Description, SAC/HSN Code, and Amount) and extract them completely. Do not omit any numbers, codes, or totals."
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                temperature=0.0
            )
            ocr_text = response.choices[0].message.content
            print(f"  OCR successful for Page {page.number + 1} (extracted {len(ocr_text)} characters).")
            return ocr_text + "\n"
        except Exception as e:
            print(f"  OCR fallback failed for Page {page.number + 1}: {e}")
            return text + "\n"
    return text + "\n"

def process_pdf_open_source(pdf_path, model_override=None):
    """Process PDF by extracting text locally and sending it to an OpenAI-compatible model, handling large PDFs by chunking.
    
    Args:
        pdf_path: Path to the PDF file.
        model_override: Optional dict with keys 'provider' and 'model' to force a specific model.
                        If None, auto-routing logic applies (<=5 pages → Groq, >5 → Ollama).
    """
    try:
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
    except Exception as e:
        print(f"  Error opening PDF {pdf_path}: {e}")
        return []
        
    if total_pages == 0:
        print(f"  Warning: PDF file {pdf_path} has 0 pages.")
        return []

    is_cloud_primary = False

    # --- Model resolution ---
    if model_override and model_override.get("provider") == "openrouter":
        # User explicitly chose an OpenRouter model
        model_name = model_override["model"]
        base_url = "https://openrouter.ai/api/v1"
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is not set in .env")
        is_cloud_primary = True
        print(f"  [Manual Override] Using OpenRouter model: {model_name}")
    elif model_override and model_override.get("provider") == "ollama":
        # User explicitly chose Ollama
        model_name = model_override.get("model") or os.getenv("OLLAMA_MODEL_NAME", "qwen2.5:7b")
        base_url = os.getenv("OLLAMA_API_BASE", "http://localhost:11434/v1")
        api_key = os.getenv("OLLAMA_API_KEY", "ollama")
        print(f"  [Manual Override] Using local Ollama model: {model_name}")
    else:
        # Auto-threshold routing:
        # If pages <= 5, use Groq (Fast Cloud VLM)
        # If pages > 5, use local Ollama (Unlimited Local VLM) to avoid rate limits
        if total_pages <= 5:
            print(f"  Page count ({total_pages}) <= 5. Auto-routing to OpenRouter (Cloud) for fast execution.")
            model_name = "meta-llama/llama-3.3-70b-instruct"
            base_url = "https://openrouter.ai/api/v1"
            api_key = os.getenv("OPENROUTER_API_KEY")
            if not api_key:
                raise ValueError("OPENROUTER_API_KEY is not set in .env")
            is_cloud_primary = True
        else:
            print(f"  Page count ({total_pages}) > 5. Auto-routing to Local Ollama to respect rate limits.")
            model_name = os.getenv("OLLAMA_MODEL_NAME", "qwen2.5:7b")
            base_url = os.getenv("OLLAMA_API_BASE", "http://localhost:11434/v1")
            api_key = os.getenv("OLLAMA_API_KEY", "ollama")
        
    from openai import OpenAI
    client = OpenAI(api_key=api_key, base_url=base_url)
    
    print(f"Processing {pdf_path} ({total_pages} pages) using open-source model ({model_name})...")
    
    # Threshold for page chunking
    CHUNK_SIZE = 3
    OVERLAP = 1
    
    all_items = []
    
    if total_pages <= CHUNK_SIZE:
        pdf_text = ""
        for page in doc:
            pdf_text += extract_page_text_with_ocr_fallback(page, client)
            
        if not pdf_text.strip():
            print("  Warning: Extracted PDF text is empty. The file might be scanned or blank.")
            return []
            
        try:
            return call_llm_for_text(pdf_text, model_name, client)
        except Exception as e:
            if is_cloud_primary:
                print(f"  Primary Cloud client failed: {e}. Falling back to local Ollama...")
                local_model = os.getenv("OLLAMA_MODEL_NAME", "qwen2.5:7b")
                local_base = os.getenv("OLLAMA_API_BASE", "http://localhost:11434/v1")
                local_key = os.getenv("OLLAMA_API_KEY", "ollama")
                local_client = OpenAI(api_key=local_key, base_url=local_base)
                try:
                    return call_llm_for_text(pdf_text, local_model, local_client)
                except Exception as ollama_err:
                    if "Connection error" in str(ollama_err):
                        raise e  # Return the original Cloud error (like rate limit) if Ollama isn't reachable
                    raise ollama_err
            else:
                raise e
    else:
        print(f"  Large document detected. Processing in chunks of {CHUNK_SIZE} pages with {OVERLAP}-page overlap...")
        start = 0
        chunk_index = 1
        while start < total_pages:
            end = min(start + CHUNK_SIZE, total_pages)
            print(f"  --- Processing Chunk {chunk_index} (Pages {start+1} to {end}) ---")
            
            chunk_text = ""
            for p_num in range(start, end):
                chunk_text += extract_page_text_with_ocr_fallback(doc[p_num], client)
                
            if chunk_text.strip():
                try:
                    items = call_llm_for_text(chunk_text, model_name, client)
                except Exception as e:
                    if is_cloud_primary:
                        print(f"  Primary Cloud client failed on chunk {chunk_index}: {e}. Falling back to local Ollama...")
                        local_model = os.getenv("OLLAMA_MODEL_NAME", "qwen2.5:7b")
                        local_base = os.getenv("OLLAMA_API_BASE", "http://localhost:11434/v1")
                        local_key = os.getenv("OLLAMA_API_KEY", "ollama")
                        local_client = OpenAI(api_key=local_key, base_url=local_base)
                        try:
                            items = call_llm_for_text(chunk_text, local_model, local_client)
                        except Exception as ollama_err:
                            if "Connection error" in str(ollama_err):
                                raise e
                            raise ollama_err
                    else:
                        raise e
                all_items.extend(items)
            else:
                print(f"  Warning: Chunk {chunk_index} has no extractable text.")
                
            if end == total_pages:
                break
                
            start += CHUNK_SIZE - OVERLAP
            chunk_index += 1
            time.sleep(2)
            
        return all_items

def process_pdf(pdf_path, model_override=None):
    return process_pdf_open_source(pdf_path, model_override=model_override)

def deduplicate_items(df):
    """
    Strict deduplication based on PRD rules:
    1. Drop exact duplicates (same invoice, same party, same amount)
    2. If same invoice number has a summary row AND breakdown rows, keep only breakdowns.
       Summary rows are identified by containing keywords like 'total', 'summary', 'subtotal',
       'payable', 'balance', 'grand total', or 'current charges' in particulars.
    3. Drop zero-value rows
    """
    if df.empty:
        return df
        
    # Step 1: Drop rows where both amount and total_amount are 0 or NaN
    df = df[~((df["AMOUNT"].fillna(0) == 0) & (df["TOTAL AMOUNT"].fillna(0) == 0))].copy()
    
    # Step 2: Handle identical amounts for the same invoice number.
    # We only drop duplicates if at least one row in the duplicate group is a summary row.
    # Otherwise, they are separate legitimate line items that happen to have the same amount.
    summary_keywords = ['total', 'summary', 'subtotal', 'payable', 'balance', 'grand total', 'current charges']
    
    def filter_duplicate_amounts(group):
        if len(group) <= 1:
            return group
        # Check if any row in this group of identical amounts looks like a summary
        is_summary = group["PARTICULARS"].astype(str).str.lower().apply(
            lambda x: any(kw in x for kw in summary_keywords)
        )
        if is_summary.any():
            # If there's a mix of detailed and summary rows, keep only non-summary rows
            non_summaries = group[~is_summary]
            if not non_summaries.empty:
                return non_summaries
            else:
                # If all are summaries, keep the first one
                return group.head(1)
        return group # Keep all if none are summaries (legitimate duplicate amounts)

    # Apply the custom grouping filter
    df = df.groupby(["SUPPLIER INV", "AMOUNT"], group_keys=False).apply(filter_duplicate_amounts)
    
    # Step 3: Standard dedup on key composite
    df = df.drop_duplicates(subset=["SUPPLIER INV", "PARTY A/C NAME", "PARTICULARS", "AMOUNT"], keep="first")
    
    return df

def build_dataframe(all_items):
    """Convert extracted items to a cleaned, deduplicated DataFrame."""
    if not all_items:
        return pd.DataFrame()
        
    records = []
    for item in all_items:
        records.append({
            "SUPPLIER INV": item.supplier_inv,
            "INVOICE DATE": item.invoice_date,
            "GST NO": item.gst_no,
            "PARTY A/C NAME": item.party_ac_name,
            "PLACE OF SUPPLY": item.place_of_supply,
            "PARTICULARS": item.particulars,
            "AMOUNT": item.amount,
            "SGST": item.sgst,
            "CGST": item.cgst,
            "IGST": item.igst,
            "TOTAL AMOUNT": item.total_amount,
            "Narration": item.narration,
            "HSN": item.hsn
        })
        
    df = pd.DataFrame(records)
    columns = ["SUPPLIER INV", "INVOICE DATE", "GST NO", "PARTY A/C NAME", "PLACE OF SUPPLY", 
               "PARTICULARS", "AMOUNT", "SGST", "CGST", "IGST", "TOTAL AMOUNT", "Narration", "HSN"]
    df = df.reindex(columns=columns)
    
    # Apply strict PRD deduplication
    df = deduplicate_items(df)
    
    return df

def main():
    parser = argparse.ArgumentParser(description="Process PDF invoices into Excel")
    parser.add_argument("input_path", help="Path to PDF file or directory containing PDFs")
    parser.add_argument("--output", default="output.xlsx", help="Output Excel filename")
    
    args = parser.parse_args()
    
    all_items = []
    
    if os.path.isfile(args.input_path) and args.input_path.lower().endswith(".pdf"):
        items = process_pdf(args.input_path)
        all_items.extend(items)
    elif os.path.isdir(args.input_path):
        for filename in os.listdir(args.input_path):
            if filename.lower().endswith(".pdf"):
                file_path = os.path.join(args.input_path, filename)
                items = process_pdf(file_path)
                all_items.extend(items)
    else:
        print("Invalid input path. Provide a PDF file or a directory.")
        return
        
    df = build_dataframe(all_items)
    
    if df.empty:
        print("No data extracted. Exiting.")
        return
    
    df.to_excel(args.output, index=False)
    print(f"Successfully saved {len(df)} unique line items to {args.output}")

if __name__ == "__main__":
    main()
