from fastapi import FastAPI, File, UploadFile, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import os
import json
import shutil
import tempfile
import pandas as pd
from typing import List, Optional, Any
from pydantic import BaseModel
import sys

# Ensure backend directory is in the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from invoice_processor import process_pdf, build_dataframe, LineItem
from gstr2b_reconciler import parse_gstr2b, reconcile as recon_match

MODEL_OPTIONS = {
    "auto": None,  # Smart routing (default)
    "openrouter-llama-3.3-70b": {"provider": "openrouter", "model": "meta-llama/llama-3.3-70b-instruct"},
    "openrouter-gemini-flash": {"provider": "openrouter", "model": "google/gemini-2.5-flash"},
    "ollama": {"provider": "ollama", "model": None},  # Uses OLLAMA_MODEL_NAME env var
}

app = FastAPI(title="AI Invoice Extractor API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust for production if needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ExportRequest(BaseModel):
    items: List[dict]

def validate_item(item: dict) -> List[str]:
    """Helper to check for potential errors/warnings in a line item."""
    errors = []
    
    # 1. Check critical fields
    if not item.get("supplier_inv"):
        errors.append("Missing invoice number")
    if not item.get("invoice_date"):
        errors.append("Missing invoice date")
    if not item.get("gst_no"):
        errors.append("Missing supplier GSTIN")
    elif len(str(item.get("gst_no")).strip()) != 15:
        errors.append("GSTIN must be exactly 15 characters")
        
    # 2. Math checks
    amount = float(item.get("amount") or 0.0)
    sgst = float(item.get("sgst") or 0.0)
    cgst = float(item.get("cgst") or 0.0)
    igst = float(item.get("igst") or 0.0)
    total_amount = float(item.get("total_amount") or 0.0)
    
    expected_total = amount + sgst + cgst + igst
    if abs(expected_total - total_amount) > 2.0:  # Allow small rounding threshold
        errors.append(f"Math mismatch: base + taxes ({expected_total:.2f}) != total ({total_amount:.2f})")
        
    return errors

@app.get("/api/models")
async def get_models():
    return JSONResponse(content={
        "models": [
            {"id": "auto",                    "name": "⚡ Auto (Smart Routing)",       "description": "≤5 pages → OpenRouter cloud, >5 pages → Local Ollama"},
            {"id": "openrouter-llama-3.3-70b","name": "☁️ OpenRouter — Llama 3.3 70B", "description": "Fast cloud model, great for standard invoices"},
            {"id": "openrouter-gemini-flash", "name": "☁️ OpenRouter — Gemini 2.5 Flash", "description": "Google's fast multimodal model via OpenRouter"},
            {"id": "ollama",                  "name": "🖥️ Local Ollama",                 "description": "Private, unlimited — runs entirely on your machine"},
        ]
    })

@app.post("/api/extract")
async def extract_invoices(files: List[UploadFile] = File(...), model: Optional[str] = None):
    tmpdirname = tempfile.mkdtemp()
    try:
        file_paths = []
        for file in files:
            file_path = os.path.join(tmpdirname, file.filename)
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            file_paths.append(file_path)
            
        # Resolve model config
        model_config = MODEL_OPTIONS.get(model or "auto")
        
        all_items = []
        for i, fp in enumerate(file_paths):
            print(f"Processing upload {i+1}: {os.path.basename(fp)} [model={model or 'auto'}]")
            items = process_pdf(fp, model_override=model_config)
            all_items.extend(items)
            
    except Exception as e:
        print(f"Extraction error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        shutil.rmtree(tmpdirname, ignore_errors=True)
        
    if not all_items:
        raise HTTPException(status_code=422, detail="No data could be extracted from the uploaded file(s).")
        
    # Convert LineItem objects to dictionaries and attach validation flags
    results = []
    for item in all_items:
        item_dict = {
            "supplier_inv": item.supplier_inv,
            "invoice_date": item.invoice_date,
            "gst_no": item.gst_no,
            "party_ac_name": item.party_ac_name,
            "place_of_supply": item.place_of_supply,
            "particulars": item.particulars,
            "amount": item.amount,
            "sgst": item.sgst,
            "cgst": item.cgst,
            "igst": item.igst,
            "total_amount": item.total_amount,
            "narration": item.narration,
            "hsn": item.hsn
        }
        item_dict["errors"] = validate_item(item_dict)
        results.append(item_dict)
        
    return JSONResponse(content={"items": results})

@app.post("/api/export")
async def export_to_excel(request: ExportRequest):
    if not request.items:
        raise HTTPException(status_code=400, detail="No items to export")
        
    records = []
    for item in request.items:
        records.append({
            "SUPPLIER INV": item.get("supplier_inv"),
            "INVOICE DATE": item.get("invoice_date"),
            "GST NO": item.get("gst_no"),
            "PARTY A/C NAME": item.get("party_ac_name"),
            "PLACE OF SUPPLY": item.get("place_of_supply"),
            "PARTICULARS": item.get("particulars"),
            "AMOUNT": float(item.get("amount") or 0.0),
            "SGST": float(item.get("sgst") or 0.0),
            "CGST": float(item.get("cgst") or 0.0),
            "IGST": float(item.get("igst") or 0.0),
            "TOTAL AMOUNT": float(item.get("total_amount") or 0.0),
            "Narration": item.get("narration"),
            "HSN": item.get("hsn")
        })
        
    df = pd.DataFrame(records)
    columns = ["SUPPLIER INV", "INVOICE DATE", "GST NO", "PARTY A/C NAME", "PLACE OF SUPPLY", 
               "PARTICULARS", "AMOUNT", "SGST", "CGST", "IGST", "TOTAL AMOUNT", "Narration", "HSN"]
    df = df.reindex(columns=columns)
    
    # Save to a temporary excel file
    output_path = os.path.join(tempfile.gettempdir(), "extracted_invoices_edited.xlsx")
    df.to_excel(output_path, index=False)
    
    return FileResponse(
        path=output_path, 
        filename="extracted_invoices.xlsx", 
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)


# ── GSTR-2B Reconciliation ────────────────────────────────────────────────────

class ReconcileRequest(BaseModel):
    items: List[dict]          # extracted invoice line items
    gstr2b: Any                # raw GSTR-2B JSON (dict) or JSON string


@app.post("/api/reconcile")
async def reconcile_gstr2b(req: ReconcileRequest):
    """
    Match extracted invoice items against GSTR-2B data.
    Returns annotated rows (with recon_status) + a summary.
    """
    try:
        raw_2b = req.gstr2b
        if isinstance(raw_2b, str):
            raw_2b = json.loads(raw_2b)

        gstr2b_records = parse_gstr2b(raw_2b)
        if not gstr2b_records:
            raise HTTPException(
                status_code=422,
                detail="No B2B invoice records found in the GSTR-2B JSON. "
                       "Please upload the full GSTR-2B JSON downloaded from the GST portal."
            )

        result = recon_match(req.items, gstr2b_records)
        return JSONResponse(content=result)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reconciliation error: {e}")


@app.post("/api/reconcile/export")
async def export_reconciliation(req: ReconcileRequest):
    """
    Run reconciliation and return a color-coded Excel file with two sheets:
      Sheet 1 — Reconciliation (all rows, color-coded by status)
      Sheet 2 — Summary (counts + amounts per status)
    """
    try:
        from openpyxl import Workbook
        from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
        from openpyxl.utils import get_column_letter

        raw_2b = req.gstr2b
        if isinstance(raw_2b, str):
            raw_2b = json.loads(raw_2b)

        gstr2b_records = parse_gstr2b(raw_2b)
        result = recon_match(req.items, gstr2b_records)
        all_rows = result["rows"] + result["extra"]
        summary  = result["summary"]

        # ── Colour map ───────────────────────────────────────────────────────
        STATUS_FILLS = {
            "matched":       PatternFill("solid", fgColor="C6EFCE"),   # green
            "mismatch":      PatternFill("solid", fgColor="FFEB9C"),   # amber
            "missing_in_2b": PatternFill("solid", fgColor="FFC7CE"),   # red
            "not_in_books":  PatternFill("solid", fgColor="BDD7EE"),   # blue
        }
        STATUS_LABELS = {
            "matched":       "✓ Matched",
            "mismatch":      "⚠ Amount Mismatch",
            "missing_in_2b": "✗ Missing in 2B",
            "not_in_books":  "ℹ Not Booked",
        }

        wb = Workbook()

        # ── Sheet 1: Reconciliation ──────────────────────────────────────────
        ws = wb.active
        ws.title = "Reconciliation"

        headers = [
            "Status", "Supplier Invoice", "Invoice Date", "GSTIN",
            "Party Name", "Particulars",
            "Books: Taxable", "Books: SGST", "Books: CGST", "Books: IGST", "Books: Total",
            "2B: Taxable", "2B: SGST", "2B: CGST", "2B: IGST", "2B: Total",
            "Difference", "HSN",
        ]

        header_fill = PatternFill("solid", fgColor="1F3864")
        header_font = Font(bold=True, color="FFFFFF", size=10)
        thin = Side(style="thin", color="CCCCCC")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)

        for col_idx, h in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_idx, value=h)
            cell.fill   = header_fill
            cell.font   = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = border

        ws.row_dimensions[1].height = 28

        for row_idx, row in enumerate(all_rows, 2):
            status = row.get("recon_status", "")
            fill   = STATUS_FILLS.get(status)

            values = [
                STATUS_LABELS.get(status, status),
                row.get("supplier_inv"),
                row.get("invoice_date"),
                row.get("gst_no"),
                row.get("party_ac_name"),
                row.get("particulars"),
                row.get("amount"),
                row.get("sgst"),
                row.get("cgst"),
                row.get("igst"),
                row.get("total_amount"),
                row.get("2b_taxable_val"),
                row.get("2b_sgst"),
                row.get("2b_cgst"),
                row.get("2b_igst"),
                row.get("2b_total_val"),
                row.get("diff_amount"),
                row.get("hsn"),
            ]
            for col_idx, val in enumerate(values, 1):
                cell = ws.cell(row=row_idx, column=col_idx, value=val)
                if fill:
                    cell.fill = fill
                cell.border = border
                cell.alignment = Alignment(vertical="center")

        # Auto-width columns
        for col_idx in range(1, len(headers) + 1):
            col_letter = get_column_letter(col_idx)
            ws.column_dimensions[col_letter].width = 18
        ws.column_dimensions["A"].width = 22  # Status
        ws.column_dimensions["E"].width = 28  # Party Name
        ws.column_dimensions["F"].width = 28  # Particulars

        ws.freeze_panes = "A2"  # freeze header

        # ── Sheet 2: Summary ─────────────────────────────────────────────────
        ws2 = wb.create_sheet("Summary")
        ws2.column_dimensions["A"].width = 26
        ws2.column_dimensions["B"].width = 14
        ws2.column_dimensions["C"].width = 18

        summary_headers = ["Status", "Count", "Total Amount (₹)"]
        for ci, h in enumerate(summary_headers, 1):
            cell = ws2.cell(row=1, column=ci, value=h)
            cell.fill   = header_fill
            cell.font   = header_font
            cell.alignment = Alignment(horizontal="center")
            cell.border = border

        summary_rows = [
            ("✓ Matched",          summary["counts"]["matched"],       summary["amounts"]["matched"],       "C6EFCE"),
            ("⚠ Amount Mismatch",  summary["counts"]["mismatch"],      summary["amounts"]["mismatch"],      "FFEB9C"),
            ("✗ Missing in 2B",    summary["counts"]["missing_in_2b"], summary["amounts"]["missing_in_2b"], "FFC7CE"),
            ("ℹ Not Booked",       summary["counts"]["not_in_books"],  summary["amounts"]["not_in_books"],  "BDD7EE"),
        ]
        for ri, (label, count, amount, color) in enumerate(summary_rows, 2):
            fill = PatternFill("solid", fgColor=color)
            for ci, val in enumerate([label, count, amount], 1):
                cell = ws2.cell(row=ri, column=ci, value=val)
                cell.fill   = fill
                cell.border = border
                cell.alignment = Alignment(horizontal="center")

        # ITC risk rows
        ws2.cell(row=7, column=1, value="ITC at Risk (Missing + Mismatch)").font = Font(bold=True, color="C00000")
        ws2.cell(row=7, column=3, value=summary["itc_at_risk"]).font           = Font(bold=True, color="C00000")
        ws2.cell(row=8, column=1, value="Matched ITC (Claimable)").font        = Font(bold=True, color="375623")
        ws2.cell(row=8, column=3, value=summary["matched_itc"]).font           = Font(bold=True, color="375623")

        output_path = os.path.join(tempfile.gettempdir(), "gstr2b_reconciliation.xlsx")
        wb.save(output_path)

        return FileResponse(
            path=output_path,
            filename="gstr2b_reconciliation.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export error: {e}")
