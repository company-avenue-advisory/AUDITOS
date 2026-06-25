import asyncio
import os
from database import SessionLocal
from models import InvoiceTask, TaskStatus, BatchJob, SalesLineItem, PurchaseLineItem
from invoice_processor import process_pdf, InvoiceExtractionResponse

# 🛑 CRITICAL ARCHITECTURE PIVOT 🛑
# Restrict concurrent LLM API calls to an absolute maximum of 20 at any given time.
llm_semaphore = asyncio.Semaphore(20)

async def extract_invoice_async(file_path: str, model_config: dict, invoice_type: str):
    """Wraps the synchronous process_pdf in an async thread, guarded by the semaphore."""
    async with llm_semaphore:
        # asyncio.to_thread runs the synchronous pdfplumber & LLM logic in a background thread
        res = await asyncio.to_thread(process_pdf, file_path, model_config, invoice_type)
        return res

async def process_batch(batch_id: str, tasks: list, model_config: dict, type_val: str):
    """
    Background task that processes an entire batch of invoices concurrently.
    The internal semaphore ensures no more than 3 hit the API at once.
    """
    from ws_manager import manager
    total = len(tasks)
    completed_count = 0
    failed_count = 0
    progress_lock = asyncio.Lock()

    async def broadcast_progress():
        async with progress_lock:
            msg = {
                "total": total,
                "completed": completed_count,
                "failed": failed_count,
                "status": "PROCESSING"
            }
            if completed_count + failed_count == total:
                msg["status"] = "COMPLETED"
        await manager.broadcast_to_batch(batch_id, msg)

    async def process_single_task(task_id: str, file_path: str):
        nonlocal completed_count, failed_count
        db = SessionLocal()
        task = db.query(InvoiceTask).filter(InvoiceTask.id == task_id).first()
        if not task:
            db.close()
            return
            
        task.status = TaskStatus.PROCESSING
        db.commit()
        
        try:
            res: InvoiceExtractionResponse = await extract_invoice_async(file_path, model_config, type_val)
            
            # Serialize the results to SQL rows
            if res.sales_items:
                for item in res.sales_items:
                    db_item = SalesLineItem(
                        task_id=task.id,
                        voucher_date=item.voucher_date,
                        voucher_type=item.voucher_type,
                        invoice_no=item.invoice_no,
                        party_ledger_name=item.party_ledger_name,
                        party_gstin=item.party_gstin,
                        place_of_supply=item.place_of_supply,
                        particulars=item.particulars,
                        hsn=item.hsn,
                        qty=item.qty,
                        rate=item.rate,
                        taxable_value=item.taxable_value,
                        discount=item.discount,
                        advances=item.advances,
                        cgst_amount=item.cgst_amount,
                        sgst_amount=item.sgst_amount,
                        igst_amount=item.igst_amount,
                        total_invoice_value=item.total_invoice_value,
                        gstr1_category=item.gstr1_category,
                        narration=item.narration
                    )
                    db.add(db_item)
                    
            if res.purchase_items:
                for item in res.purchase_items:
                    db_item = PurchaseLineItem(
                        task_id=task.id,
                        voucher_date=item.voucher_date,
                        voucher_type=item.voucher_type,
                        invoice_no=item.invoice_no,
                        party_ledger_name=item.party_ledger_name,
                        party_gstin=item.party_gstin,
                        place_of_supply=item.place_of_supply,
                        particulars=item.particulars,
                        hsn=item.hsn,
                        qty=item.qty,
                        rate=item.rate,
                        taxable_value=item.taxable_value,
                        cgst_amount=item.cgst_amount,
                        sgst_amount=item.sgst_amount,
                        igst_amount=item.igst_amount,
                        total_invoice_value=item.total_invoice_value,
                        itc_eligibility=item.itc_category,
                        narration=item.narration
                    )
                    db.add(db_item)
            
            task.status = TaskStatus.COMPLETED
            db.commit()
            async with progress_lock:
                completed_count += 1
        except Exception as e:
            task.error_message = str(e)
            task.status = TaskStatus.FAILED
            db.commit()
            async with progress_lock:
                failed_count += 1
        finally:
            db.close()
            await broadcast_progress()
            # We keep the temp file so the Side-by-Side viewer can display it
            pass

    # Create awaitable coroutines for all tasks in the batch
    coroutines = [process_single_task(t['id'], t['file_path']) for t in tasks]
    
    # Run them concurrently. The semaphore inside extract_invoice_async will throttle them.
    await asyncio.gather(*coroutines)
    
    # Check if batch is fully complete and update batch status
    db = SessionLocal()
    batch = db.query(BatchJob).filter(BatchJob.id == batch_id).first()
    if batch:
        all_tasks = db.query(InvoiceTask).filter(InvoiceTask.batch_id == batch_id).all()
        completed = sum(1 for t in all_tasks if t.status == TaskStatus.COMPLETED)
        failed = sum(1 for t in all_tasks if t.status == TaskStatus.FAILED)
        if completed + failed == len(all_tasks) and len(all_tasks) > 0:
            batch.status = TaskStatus.COMPLETED
            db.commit()
    db.close()
