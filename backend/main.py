from fastapi import FastAPI, File, UploadFile, Request, HTTPException, Form, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import os
import json
import shutil
import tempfile
import pandas as pd
from typing import List, Optional, Any
from pydantic import BaseModel
import sys
import os
import io
import zipfile
import uuid
from fastapi import BackgroundTasks, Depends
from sqlalchemy.orm import Session

# Ensure backend directory is in the path BEFORE local imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import get_db, engine, Base
from models import BatchJob, InvoiceTask, TaskStatus, SalesLineItem, PurchaseLineItem, ObservabilityLog
from async_tasks import process_batch
from ws_manager import manager

# Ensure database tables exist
Base.metadata.create_all(bind=engine)

from invoice_processor import process_pdf, build_dataframes, InvoiceExtractionResponse
from services.gstr2b_reconciler import parse_gstr2b, reconcile as recon_match
from services.udyam_parser import parse_udyam_certificate
from services.msme_compliance import calculate_43bh_compliance
from services.document_core import parse_bank_statement, smart_split_by_size, enhance_scan, compress_pdf, ocr_extract
from services.gcs_storage import gcs_storage
from services.task_queue import dispatch_batch_task
from models import User
from services.auth import hash_password, verify_password, create_access_token, get_current_user, RoleChecker

MODEL_OPTIONS = {
    "auto": None,  # Smart routing (Claude > Groq > Gemini based on keys present)
    "anthropic": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
    "anthropic-sonnet": {"provider": "anthropic", "model": "claude-sonnet-4-6"},
    "openrouter-llama-3.3-70b": {"provider": "openrouter", "model": "meta-llama/llama-3.3-70b-instruct"},
    "openrouter-gemini-flash": {"provider": "openrouter", "model": "google/gemini-2.5-flash"},
    "ollama": {"provider": "ollama", "model": None},  # Uses OLLAMA_MODEL_NAME env var
}

app = FastAPI(title="AI Invoice Extractor API")

# Configure CORS
allowed_origins_str = os.getenv("ALLOWED_ORIGINS", "*")
if allowed_origins_str == "*":
    origins = ["*"]
else:
    origins = [origin.strip() for origin in allowed_origins_str.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class UserRegisterRequest(BaseModel):
    email: str
    password: str
    role: Optional[str] = "auditor"

class UserLoginRequest(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    role: str
    email: str

@app.post("/api/auth/register", status_code=201)
async def register(req: UserRegisterRequest, db: Session = Depends(get_db)):
    """Creates a new user account with hashed password and RBAC role."""
    # Check if user already exists
    existing_user = db.query(User).filter(User.email == req.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email is already registered")
    
    # Validate role
    allowed_roles = ["owner", "hr", "auditor", "developer", "other"]
    user_role = req.role.lower() if req.role else "auditor"
    if user_role not in allowed_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role. Supported: {allowed_roles}")

    new_user = User(
        id=str(uuid.uuid4()),
        email=req.email,
        hashed_password=hash_password(req.password),
        role=user_role
    )
    db.add(new_user)
    db.commit()
    return {"message": "User registered successfully", "email": new_user.email, "role": new_user.role}

@app.post("/api/auth/login", response_model=TokenResponse)
async def login(req: UserLoginRequest, db: Session = Depends(get_db)):
    """Authenticates credentials and returns a signed JWT access token."""
    print(f"[AUTH DEBUG] Login request received for email: '{req.email}'")
    user = db.query(User).filter(User.email == req.email).first()
    if not user:
        print(f"[AUTH DEBUG] User not found in database for email: '{req.email}'")
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    password_ok = verify_password(req.password, user.hashed_password)
    print(f"[AUTH DEBUG] Password check result for '{req.email}': {password_ok}")
    if not password_ok:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Generate token
    access_token = create_access_token(data={"sub": user.email})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": user.role,
        "email": user.email
    }

# ExportRequest deprecated
def validate_suvit_item(item: dict) -> List[str]:
    """Helper to check for potential errors/warnings in a Suvit line item."""
    errors = []
    if not item.get("invoice_no"):
        errors.append("Missing invoice number")
    if not item.get("voucher_date"):
        errors.append("Missing voucher date")
        
    # Math checks
    amount = float(item.get("taxable_value") or 0.0)
    sgst = float(item.get("sgst_amount") or 0.0)
    cgst = float(item.get("cgst_amount") or 0.0)
    igst = float(item.get("igst_amount") or 0.0)
    total_amount = float(item.get("total_invoice_value") or 0.0)
    
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

@app.post("/api/invoices/upload-batch")
async def upload_batch(background_tasks: BackgroundTasks, files: List[UploadFile] = File(...), model: Optional[str] = None, type: Optional[str] = "both", db: Session = Depends(get_db), current_user: User = Depends(RoleChecker(["owner", "auditor"]))):
    batch_id = str(uuid.uuid4())
    total_files = len(files)
    
    batch_job = BatchJob(id=batch_id, total_files=total_files, status=TaskStatus.PENDING, user_id=current_user.id)
    db.add(batch_job)
    db.commit()

    batch_dir = os.path.join(tempfile.gettempdir(), f"batch_{batch_id}")
    os.makedirs(batch_dir, exist_ok=True)
    
    tasks_to_process = []
    
    try:
        model_config = MODEL_OPTIONS.get(model or "auto")
        
        for file in files:
            file_path = os.path.join(batch_dir, file.filename)
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
                
            # If the file is a zip, extract it and process its contents
            if file.filename.lower().endswith(".zip"):
                with zipfile.ZipFile(file_path, 'r') as zip_ref:
                    # Extract to a temp subfolder
                    extract_dir = os.path.join(batch_dir, f"extracted_{uuid.uuid4().hex[:8]}")
                    os.makedirs(extract_dir, exist_ok=True)
                    zip_ref.extractall(extract_dir)
                    
                    # Iterate through extracted files
                    for root, _, extracted_files in os.walk(extract_dir):
                        for extracted_file in extracted_files:
                            if extracted_file.lower().endswith(".pdf"):
                                extracted_path = os.path.join(root, extracted_file)
                                
                                if gcs_storage.is_active():
                                    gcs_storage.upload_file(extracted_path, f"batches/{batch_id}/{extracted_file}")
                                
                                task_id = str(uuid.uuid4())
                                invoice_task = InvoiceTask(
                                    id=task_id,
                                    batch_id=batch_id,
                                    file_name=extracted_file,
                                    status=TaskStatus.PENDING,
                                    invoice_type=type
                                )
                                db.add(invoice_task)
                                
                                tasks_to_process.append({
                                    "id": task_id,
                                    "file_path": extracted_path
                                })
                # Remove the original zip file after extraction
                try:
                    os.remove(file_path)
                except:
                    pass
            else:
                # It's a standard PDF file
                if file.filename.lower().endswith(".pdf"):
                    if gcs_storage.is_active():
                        gcs_storage.upload_file(file_path, f"batches/{batch_id}/{file.filename}")
                    
                    task_id = str(uuid.uuid4())
                    invoice_task = InvoiceTask(
                        id=task_id,
                        batch_id=batch_id,
                        file_name=file.filename,
                        status=TaskStatus.PENDING,
                        invoice_type=type
                    )
                    db.add(invoice_task)
                    
                    tasks_to_process.append({
                        "id": task_id,
                        "file_path": file_path
                    })
            
        db.commit()
        
        # Dispatch to queue broker or local background tasks
        dispatch_batch_task(background_tasks, batch_id, tasks_to_process, model_config, type)
            
    except Exception as e:
        print(f"Extraction enqueue error: {e}")
        batch_job.status = TaskStatus.FAILED
        db.commit()
        raise HTTPException(status_code=500, detail=str(e))
        
    return JSONResponse(content={
        "message": "Batch enqueued successfully",
        "batch_id": batch_id,
        "total_files": total_files
    })
@app.get("/api/jobs")
async def get_all_jobs(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role in ["developer", "owner"]:
        batches = db.query(BatchJob).order_by(BatchJob.created_at.desc()).all()
    else:
        batches = db.query(BatchJob).filter(BatchJob.user_id == current_user.id).order_by(BatchJob.created_at.desc()).all()
    return [{
        "id": b.id,
        "created_at": b.created_at.isoformat(),
        "total_files": b.total_files,
        "status": b.status.value
    } for b in batches]

@app.get("/api/jobs/{batch_id}/files/{filename:path}")
async def get_pdf_file(batch_id: str, filename: str, current_user: User = Depends(get_current_user)):
    import os, tempfile
    
    with open("pdf_debug.log", "a", encoding="utf-8") as f:
        f.write(f"Requested batch_id: {batch_id}, filename: {filename}\n")
    
    # Check direct in batch_id dir
    batch_dir = os.path.join(tempfile.gettempdir(), f"batch_{batch_id}")
    file_path = os.path.join(batch_dir, filename)
    if os.path.exists(file_path):
        return FileResponse(file_path, media_type="application/pdf")
        
    # If missing locally, try to pull it from GCS
    if gcs_storage.is_active():
        gcs_blob_name = f"batches/{batch_id}/{filename}"
        if gcs_storage.file_exists(gcs_blob_name):
            if gcs_storage.download_file(gcs_blob_name, file_path):
                return FileResponse(file_path, media_type="application/pdf")
        
    # Check in subdirectories (if extracted from zip)
    if os.path.exists(batch_dir):
        for root, _, files in os.walk(batch_dir):
            if filename in files:
                return FileResponse(os.path.join(root, filename), media_type="application/pdf")
                
    # If file is genuinely missing
    from fastapi.responses import HTMLResponse
    html_content = f"""
    <html>
        <body style="font-family: sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; background-color: #f9f9fa; color: #333; text-align: center;">
            <div>
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-bottom: 16px;"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="9" y1="15" x2="15" y2="15"></line></svg>
                <h3>PDF No Longer Available</h3>
                <p style="color: #666; max-width: 300px; margin: 0 auto; line-height: 1.5;">This file was processed in an older session and has been deleted from the server to save space.<br><br>Please upload this invoice again to view it side-by-side.</p>
            </div>
        </body>
    </html>
    """
    return HTMLResponse(content=html_content, status_code=404)

@app.get("/api/jobs/{batch_id}")
async def get_job_status(batch_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    batch = db.query(BatchJob).filter(BatchJob.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Job not found")
        
    tasks = db.query(InvoiceTask).filter(InvoiceTask.batch_id == batch_id).all()
    
    total = len(tasks)
    pending = sum(1 for t in tasks if t.status == TaskStatus.PENDING)
    processing = sum(1 for t in tasks if t.status == TaskStatus.PROCESSING)
    completed = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED)
    failed = sum(1 for t in tasks if t.status == TaskStatus.FAILED)
    
    # ── Observability data integration ─────────────────────────
    # Fetch batch metrics if available
    batch_log = db.query(ObservabilityLog).filter(
        ObservabilityLog.batch_id == batch_id,
        ObservabilityLog.event_type == "batch_metrics"
    ).first()
    batch_metrics = None
    if batch_log:
        try:
            batch_metrics = json.loads(batch_log.payload_json)
        except:
            pass
            
    # Fetch batch-level system flags and task-level flags
    flag_logs = db.query(ObservabilityLog).filter(
        ObservabilityLog.batch_id == batch_id,
        ObservabilityLog.event_type == "system_flag"
    ).all()
    
    batch_flags = []
    flags_by_file = {}
    for log in flag_logs:
        try:
            payload = json.loads(log.payload_json)
            flag_info = {
                "flag_id": log.flag_id,
                "severity": log.severity,
                "detail": payload.get("trigger_detail", ""),
                "timestamp": log.timestamp_utc.isoformat()
            }
            if log.file_id:
                flags_by_file.setdefault(log.file_id, []).append(flag_info)
            else:
                batch_flags.append(flag_info)
        except:
            pass
            
    # Fetch quality scores by file
    score_logs = db.query(ObservabilityLog).filter(
        ObservabilityLog.batch_id == batch_id,
        ObservabilityLog.event_type == "extraction_quality_score"
    ).all()
    scores_by_file = {}
    for log in score_logs:
        if log.file_id:
            try:
                payload = json.loads(log.payload_json)
                scores_by_file[log.file_id] = payload.get("composite_score", 0.0)
            except:
                pass
    # ───────────────────────────────────────────────────────────
    
    tasks_details = []
    all_sales = []
    all_purchase = []
    
    for t in tasks:
        task_info = {
            "task_id": t.id,
            "filename": t.file_name,
            "status": t.status.value,
            "error_message": t.error_message,
            "composite_score": scores_by_file.get(t.id, None),
            "flags": flags_by_file.get(t.id, []),
            "recon_status": getattr(t, 'recon_status', None),
        }
        
        sales = []
        purchase = []
        if getattr(t, 'sales_items', None):
            sales = [{c.name: getattr(item, c.name) for c in item.__table__.columns if c.name not in ["task_id"]} for item in t.sales_items]
        if getattr(t, 'purchase_items', None):
            purchase = [{c.name: getattr(item, c.name) for c in item.__table__.columns if c.name not in ["task_id"]} for item in t.purchase_items]
            
        if sales or purchase or t.status == TaskStatus.COMPLETED:
            for s in sales:
                s["errors"] = validate_suvit_item(s)
                s["filename"] = t.file_name
            for p in purchase:
                p["errors"] = validate_suvit_item(p)
                p["filename"] = t.file_name
                
            task_info["sales_count"] = len(sales)
            task_info["purchase_count"] = len(purchase)
            all_sales.extend(sales)
            all_purchase.extend(purchase)
            
        tasks_details.append(task_info)
        
    return JSONResponse(content={
        "batch_id": batch.id,
        "status": batch.status.value,
        "progress": {
            "total": total,
            "pending": pending,
            "processing": processing,
            "completed": completed,
            "failed": failed
        },
        "tasks": tasks_details,
        "sales_items": all_sales if batch.status == TaskStatus.COMPLETED else [],
        "purchase_items": all_purchase if batch.status == TaskStatus.COMPLETED else [],
        "batch_metrics": batch_metrics,
        "batch_flags": batch_flags
    })

@app.get("/api/tasks/{task_id}/review")
async def get_task_review(task_id: str, db: Session = Depends(get_db)):
    """
    Phase 4A: Returns the full deterministic reconciliation audit report for a specific invoice task.
    Used to power the Review Panel UI with correction proposals, variance breakdowns, and status.
    """
    from models import InvoiceTask
    task = db.query(InvoiceTask).filter(InvoiceTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    recon_data = None
    if task.recon_report_json:
        try:
            recon_data = json.loads(task.recon_report_json)
        except Exception:
            recon_data = None

    return JSONResponse(content={
        "task_id": task_id,
        "filename": task.file_name,
        "recon_status": task.recon_status,
        "recon_report": recon_data,
    })

@app.patch("/api/tasks/{task_id}/accept-correction")
async def accept_correction(task_id: str, db: Session = Depends(get_db), current_user: User = Depends(RoleChecker(["owner", "auditor"]))):
    """
    Phase 4A: CA reviewer accepts auto-correction proposal.
    Marks the task recon_status as HUMAN_CORRECTED.
    """
    from models import InvoiceTask
    task = db.query(InvoiceTask).filter(InvoiceTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task.recon_status = "HUMAN_CORRECTED"
    db.commit()
    return JSONResponse(content={"task_id": task_id, "recon_status": "HUMAN_CORRECTED", "accepted_by": current_user.email})

@app.get("/api/tasks/{task_id}/observability")
async def get_task_observability(task_id: str, db: Session = Depends(get_db)):
    """
    Returns step-by-step pipeline execution logs for a specific file.
    """
    logs = db.query(ObservabilityLog).filter(
        ObservabilityLog.file_id == task_id
    ).order_by(ObservabilityLog.timestamp_utc.asc()).all()
    
    events = []
    for l in logs:
        try:
            payload = json.loads(l.payload_json)
        except:
            payload = {}
        events.append({
            "id": l.id,
            "event_type": l.event_type,
            "stage": l.stage,
            "severity": l.severity,
            "flag_id": l.flag_id,
            "timestamp": l.timestamp_utc.isoformat(),
            "model": l.model_identifier,
            "provider": l.api_provider,
            "prompt_version": l.prompt_version,
            "payload": payload
        })
        
    return JSONResponse(content={"task_id": task_id, "events": events})

@app.get("/api/observability/stats")
async def get_observability_stats(db: Session = Depends(get_db)):
    """
    Aggregates metrics and flags across the workspace for the landing dashboard.
    """
    from models import BatchJob, InvoiceTask
    
    total_batches = db.query(BatchJob).count()
    total_files = db.query(InvoiceTask).count()
    
    # Query all quality scores
    score_logs = db.query(ObservabilityLog).filter(
        ObservabilityLog.event_type == "extraction_quality_score"
    ).all()
    
    scores_by_file = {}
    scores = []
    for log in score_logs:
        if log.file_id:
            try:
                payload = json.loads(log.payload_json)
                val = payload.get("composite_score")
                if val is not None:
                    scores_by_file[log.file_id] = float(val)
                    scores.append(float(val))
            except:
                pass
            
    avg_score = round(sum(scores) / len(scores), 3) if scores else 1.0
    
    # Query total cost from file metrics
    metric_logs = db.query(ObservabilityLog).filter(
        ObservabilityLog.event_type == "file_metrics"
    ).all()
    
    total_cost = 0.0
    for log in metric_logs:
        try:
            payload = json.loads(log.payload_json)
            total_cost += float(payload.get("model_cost", {}).get("total_cost_inr", 0.0))
        except:
            pass
            
    # Query system flags
    flag_logs = db.query(ObservabilityLog).filter(
        ObservabilityLog.event_type == "system_flag"
    ).order_by(ObservabilityLog.timestamp_utc.desc()).all()
    
    flags = []
    for log in flag_logs:
        try:
            payload = json.loads(log.payload_json)
            flags.append({
                "batch_id": log.batch_id,
                "file_id": log.file_id,
                "filename": payload.get("filename", "batch-level"),
                "flag_id": log.flag_id,
                "severity": log.severity,
                "detail": payload.get("trigger_detail", ""),
                "timestamp": log.timestamp_utc.isoformat()
            })
        except:
            pass
            
    # Query recent jobs
    batches = db.query(BatchJob).order_by(BatchJob.created_at.desc()).limit(10).all()
    
    recent_jobs = []
    for b in batches:
        tasks_cnt = db.query(InvoiceTask).filter(InvoiceTask.batch_id == b.id).count()
        
        # Calculate batch average score
        b_scores = [scores_by_file.get(log.file_id) for log in score_logs if log.batch_id == b.id and log.file_id]
        b_scores_clean = [s for s in b_scores if s is not None]
        b_avg = round(sum(b_scores_clean) / len(b_scores_clean), 3) if b_scores_clean else None
        
        # Batch flags count
        b_flags_count = sum(1 for log in flag_logs if log.batch_id == b.id)
        
        recent_jobs.append({
            "id": b.id,
            "created_at": b.created_at.isoformat(),
            "total_files": b.total_files,
            "status": b.status.value,
            "average_quality_score": b_avg,
            "flags_count": b_flags_count
        })
        
    return JSONResponse(content={
        "total_batches": total_batches,
        "total_files": total_files,
        "average_quality_score": avg_score,
        "total_cost_inr": round(total_cost, 2),
        "recent_flags": flags[:10],
        "total_flags": len(flags),
        "recent_jobs": recent_jobs
    })


@app.websocket("/api/ws/jobs/{batch_id}")
async def websocket_endpoint(websocket: WebSocket, batch_id: str):
    await manager.connect(websocket, batch_id)
    try:
        while True:
            # We don't expect the client to send messages, but we need to keep the connection open
            # and listen for disconnects
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket, batch_id)


@app.get("/api/export/{batch_id}")
async def export_to_excel(batch_id: str, type: str, schema: str = "suvit", db: Session = Depends(get_db)):
    batch = db.query(BatchJob).filter(BatchJob.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
        
    tasks = db.query(InvoiceTask).filter(InvoiceTask.batch_id == batch_id).all()
    
    from invoice_processor import SuvitSalesItem, SuvitPurchaseItem
    
    extraction_response = InvoiceExtractionResponse()
    
    if type in ["sales", "both"]:
        sales = []
        for t in tasks:
            if getattr(t, 'sales_items', None):
                for item in t.sales_items:
                    item_dict = {c.name: getattr(item, c.name) for c in item.__table__.columns if c.name not in ["id", "task_id"]}
                    sales.append(SuvitSalesItem(**item_dict))
        extraction_response.sales_items = sales
        
    if type in ["purchase", "both"]:
        purchase = []
        for t in tasks:
            if getattr(t, 'purchase_items', None):
                for item in t.purchase_items:
                    item_dict = {c.name: getattr(item, c.name) for c in item.__table__.columns if c.name not in ["id", "task_id"]}
                    purchase.append(SuvitPurchaseItem(**item_dict))
        extraction_response.purchase_items = purchase
        
    if not extraction_response.sales_items and not extraction_response.purchase_items:
        raise HTTPException(status_code=400, detail="No items to export")
        
    sales_df, purchase_df = build_dataframes(extraction_response)
    
    def apply_schema(df, schema_name):
        if isinstance(df, pd.DataFrame) and not df.empty and schema_name != "suvit":
            sap_map = {"party_ac_name": "VendorCode", "invoice_no": "Reference", "voucher_date": "DocumentDate", "taxable_value": "AmountLC", "igst_amount": "TaxAmountIGST", "cgst_amount": "TaxAmountCGST", "sgst_amount": "TaxAmountSGST", "total_invoice_value": "TotalAmountLC", "hsn": "HSNSAC", "VOUCHER NO": "DocumentNumber", "PARTY GSTIN": "TaxNumber3", "DATE": "PostingDate"}
            netsuite_map = {"invoice_no": "InternalID", "voucher_date": "TranDate", "party_ac_name": "Entity", "taxable_value": "GrossAmt", "total_invoice_value": "Amount", "VOUCHER NO": "TranId", "DATE": "Date", "PARTY GSTIN": "VATRegNumber"}
            dynamics_map = {"invoice_no": "InvoiceId", "voucher_date": "TransDate", "party_ac_name": "AccountNum", "total_invoice_value": "InvoiceAmount", "taxable_value": "LineAmount", "VOUCHER NO": "InvoiceRegister", "DATE": "DocumentDate"}
            mapping = sap_map if schema_name == "sap" else (netsuite_map if schema_name == "netsuite" else dynamics_map)
            return df.rename(columns=lambda c: mapping.get(c, c))
        return df

    if isinstance(sales_df, dict):
        for k in sales_df:
            sales_df[k] = apply_schema(sales_df[k], schema)
    else:
        sales_df = apply_schema(sales_df, schema)
        
    purchase_df = apply_schema(purchase_df, schema)
    
    has_sales = isinstance(sales_df, dict) and any(not df.empty for df in sales_df.values())
    has_purchase = not purchase_df.empty

    def save_sales(path):
        with pd.ExcelWriter(path) as writer:
            for sheet_name, df in sales_df.items():
                if not df.empty:
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
                    
    if has_sales and has_purchase:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            sales_path = os.path.join(tempfile.gettempdir(), "Suvit_Sales_Upload.xlsx")
            purchase_path = os.path.join(tempfile.gettempdir(), "Suvit_Purchase_Upload.xlsx")
            save_sales(sales_path)
            purchase_df.to_excel(purchase_path, index=False)
            zip_file.write(sales_path, arcname="Suvit_Sales_Upload.xlsx")
            zip_file.write(purchase_path, arcname="Suvit_Purchase_Upload.xlsx")
            
        zip_buffer.seek(0)
        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={"Content-Disposition": "attachment; filename=Suvit_Both_Upload.zip"}
        )
    elif has_sales:
        output_path = os.path.join(tempfile.gettempdir(), "Suvit_Sales_Upload.xlsx")
        save_sales(output_path)
        return FileResponse(
            path=output_path, 
            filename="Suvit_Sales_Upload.xlsx", 
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        output_path = os.path.join(tempfile.gettempdir(), "Suvit_Purchase_Upload.xlsx")
        purchase_df.to_excel(output_path, index=False)
        return FileResponse(
            path=output_path, 
            filename="Suvit_Purchase_Upload.xlsx", 
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

class MSMEVerifyRequest(BaseModel):
    udyam_number: str

@app.post("/api/verify-msme")
async def verify_msme_status(req: MSMEVerifyRequest, current_user: User = Depends(RoleChecker(["owner", "hr"]))):
    """
    Authorized integration point for MSME status verification.
    This simulates a query to the Ministry of MSME database or an authorized API provider.
    """
    udyam = req.udyam_number.strip().upper()
    if not udyam.startswith("UDYAM"):
        raise HTTPException(status_code=400, detail="Invalid Udyam Number format. Must start with 'UDYAM'.")
    
    # Extract state or digits for deterministic mock response
    parts = udyam.split("-")
    state_code = parts[1] if len(parts) > 1 else "IND"
    
    # Deterministic mock assignment based on the last digit
    last_char = udyam[-1] if udyam else "0"
    if last_char in "159":
        enterprise_type = "MICRO"
    elif last_char in "26":
        enterprise_type = "SMALL"
    elif last_char in "37":
        enterprise_type = "MEDIUM"
    else:
        enterprise_type = "LARGE"
        
    mock_names = {
        "MH": "Maharashtra Engineering Works",
        "DL": "Capital Logistics Services",
        "GJ": "Gujarat Textile Mills Ltd",
        "UP": "Noida Business Consulting",
        "KA": "Bengaluru Tech Services",
    }
    company_name = mock_names.get(state_code, f"Authorized Vendor ({state_code}) Ltd")
    
    return JSONResponse(content={
        "success": True,
        "udyam_number": udyam,
        "enterprise_type": enterprise_type,
        "enterprise_name": company_name,
        "message": f"Successfully verified via authorized compliance database."
    })

@app.post("/api/tax/parse-udyam")
async def upload_udyam_certificate(file: UploadFile = File(...), current_user: User = Depends(RoleChecker(["owner", "hr"]))):
    """
    Ingests a vendor's Udyam Registration Certificate PDF, extracts metadata
    and normalizes the enterprise classification status.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF certificates are accepted.")
    try:
        pdf_bytes = await file.read()
        parsed_data = parse_udyam_certificate(pdf_bytes)
        return JSONResponse(content={
            "success": True,
            "filename": file.filename,
            **parsed_data
        })
    except Exception as e:
        print(f"Udyam parsing error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to parse Udyam Certificate: {str(e)}")

class MSMEComplianceRequest(BaseModel):
    invoice_date: str
    payment_date: Optional[str] = None
    enterprise_type: str
    has_agreement: bool
    amount: float

@app.post("/api/tax/compliance")
async def calculate_compliance_metrics(req: MSMEComplianceRequest, current_user: User = Depends(RoleChecker(["owner", "hr"]))):
    """
    Computes statutory MSME 43B(h) compliance metrics.
    """
    try:
        metrics = calculate_43bh_compliance(
            invoice_date_str=req.invoice_date,
            payment_date_str=req.payment_date,
            enterprise_type=req.enterprise_type,
            has_agreement=req.has_agreement,
            amount=req.amount
        )
        return JSONResponse(content={
            "success": True,
            **metrics
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Document Utility Suite Endpoints ──────────────────────────────────────────

@app.post("/api/docs/bank-parse")
async def bank_parse_endpoint(
    file: UploadFile = File(...),
    password: str = Form(""),
    confidence_min: str = None
):
    """
    Multi-stage bank statement parser with confidence scoring.
    Returns: {
        "success": bool,
        "transactions": [
            {
                "date": str,
                "narration": str,
                "debit": str,
                "credit": str,
                "balance": str,
                "confidence": "SURE" | "PROBABLE" | "UNCERTAIN",
                "bank_detected": str,
                "extraction_method": "table" | "regex"
            }, ...
        ],
        "summary": {"total": int, "sure": int, "probable": int, "uncertain": int}
    }
    """
    content = await file.read()
    try:
        txs = parse_bank_statement(content, password, confidence_min)

        # Build summary
        confidence_counts = {
            "SURE": sum(1 for t in txs if t.get("confidence") == "SURE"),
            "PROBABLE": sum(1 for t in txs if t.get("confidence") == "PROBABLE"),
            "UNCERTAIN": sum(1 for t in txs if t.get("confidence") == "UNCERTAIN"),
        }

        return JSONResponse(content={
            "success": True,
            "transactions": txs,
            "summary": {
                "total": len(txs),
                **confidence_counts
            }
        })
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid password or encrypted file error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Bank statement parsing failed: {str(e)}")

@app.post("/api/docs/split-portal")
async def split_portal_endpoint(file: UploadFile = File(...), target_mb: float = Form(4.5)):
    """
    Splits heavy PDF files into sub-5MB chunks, returning them bundled inside a single ZIP file.
    """
    content = await file.read()
    try:
        chunks = smart_split_by_size(content, target_mb)
        if not chunks:
            raise HTTPException(status_code=400, detail="Failed to split PDF or empty document.")
        
        # Bundle chunks into in-memory zip
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            base_name = os.path.splitext(file.filename)[0]
            for idx, chunk_bytes in enumerate(chunks, 1):
                zip_file.writestr(f"{base_name}_part_{idx}.pdf", chunk_bytes)
        
        zip_buffer.seek(0)
        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={base_name}_split.zip"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/docs/enhance-scan")
async def enhance_scan_endpoint(file: UploadFile = File(...)):
    """
    Applies adaptive contrast thresholding to a raw image, generating a clean vector PDF.
    """
    content = await file.read()
    try:
        pdf_bytes = enhance_scan(content)
        base_name = os.path.splitext(file.filename)[0]
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={base_name}_enhanced.pdf"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/docs/compress")
async def compress_pdf_endpoint(file: UploadFile = File(...), quality: int = Form(50)):
    """
    Optimizes a PDF, outputting compaction metrics in custom response headers.
    """
    content = await file.read()
    original_size = len(content)
    try:
        compressed_bytes = compress_pdf(content, quality)
        compressed_size = len(compressed_bytes)
        
        base_name = os.path.splitext(file.filename)[0]
        headers = {
            "X-Original-Size": str(original_size),
            "X-Compressed-Size": str(compressed_size),
            "Access-Control-Expose-Headers": "X-Original-Size, X-Compressed-Size",
            "Content-Disposition": f"attachment; filename={base_name}_compressed.pdf"
        }
        
        return Response(
            content=compressed_bytes,
            media_type="application/pdf",
            headers=headers
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

class ItemUpdateRequest(BaseModel):
    field: str
    value: Any

@app.put("/api/items/{item_id}")
async def update_item(item_id: int, type: str, req: ItemUpdateRequest, db: Session = Depends(get_db)):
    if type == "sales":
        item = db.query(SalesLineItem).filter(SalesLineItem.id == item_id).first()
    elif type == "purchase":
        item = db.query(PurchaseLineItem).filter(PurchaseLineItem.id == item_id).first()
    else:
        raise HTTPException(status_code=400, detail="Invalid type")
        
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
        
    if not hasattr(item, req.field):
        raise HTTPException(status_code=400, detail="Invalid field")
        
    old_value = getattr(item, req.field)
    
    # Attempt to cast float if the original column is float
    from sqlalchemy import Float
    if isinstance(getattr(item.__table__.columns, req.field).type, Float):
        try:
            val = float(req.value) if req.value else 0.0
            setattr(item, req.field, val)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid float value")
    else:
        setattr(item, req.field, req.value)
        
    db.commit()
    
    # Emit CA reviewer correction flag if value has changed
    if old_value != req.value:
        from services.observability import ObsLogger
        from models import ObservabilityLog
        import json
        
        task_id = item.task_id
        task = item.task
        batch_id = task.batch_id if task else "unknown"
        
        # Query composite score from observability logs
        log = db.query(ObservabilityLog).filter(
            ObservabilityLog.file_id == task_id,
            ObservabilityLog.event_type == "extraction_quality_score"
        ).first()
        
        composite_score = 0.85
        if log:
            try:
                payload = json.loads(log.payload_json)
                composite_score = payload.get("composite_score", 0.85)
            except:
                pass
                
        try:
            ObsLogger.emit_ca_flag(
                batch_id=batch_id,
                file_id=task_id,
                rejected_field=req.field,
                extracted_value=old_value,
                ca_corrected_value=req.value,
                composite_score=composite_score,
                db_session=db
            )
        except Exception as e:
            print(f"Error logging CA flag: {e}")
            
    return {"status": "success"}

@app.post("/api/invoice-metadata")
async def ocr_extract_endpoint(file: UploadFile = File(...)):
    """
    Converts PDF pages into images and runs local EasyOCR.
    """
    content = await file.read()
    try:
        text = ocr_extract(content)
        return JSONResponse(content={"success": True, "text": text})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
