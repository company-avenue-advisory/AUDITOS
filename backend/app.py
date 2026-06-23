from fastapi import FastAPI, File, UploadFile, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import os
import shutil
import tempfile
import pandas as pd
from invoice_processor import process_pdf, build_dataframe

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/upload")
async def upload_files(files: list[UploadFile] = File(...)):
    # Use a manual temp directory with ignore_cleanup_errors for Windows compatibility
    tmpdirname = tempfile.mkdtemp()
    try:
        # Save all uploaded files first
        file_paths = []
        for file in files:
            file_path = os.path.join(tmpdirname, file.filename)
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            file_paths.append(file_path)
        
        # Process PDFs one at a time to respect free-tier rate limits (10 RPM)
        all_items = []
        for i, fp in enumerate(file_paths):
            print(f"\n--- File {i+1}/{len(file_paths)}: {os.path.basename(fp)} ---")
            items = process_pdf(fp)
            all_items.extend(items)
            
    finally:
        # Best-effort cleanup
        try:
            shutil.rmtree(tmpdirname, ignore_errors=True)
        except Exception:
            pass
            
    if not all_items:
        return JSONResponse(
            status_code=422,
            content={"error": "No data could be extracted. The API rate limit may have been reached. Please wait 1 minute and try again with fewer files."}
        )
    
    # Use shared build_dataframe which applies PRD deduplication rules
    df = build_dataframe(all_items)
    
    if df.empty:
        return JSONResponse(
            status_code=422,
            content={"error": "No valid data extracted after applying quality filters."}
        )
    
    output_path = os.path.join(tempfile.gettempdir(), "extracted_invoices.xlsx")
    df.to_excel(output_path, index=False)
    
    return FileResponse(
        path=output_path, 
        filename="extracted_invoices.xlsx", 
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
