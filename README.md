# AntiGravity CA-Level Invoice Auditor

An enterprise-grade, highly-accurate AI pipeline designed to extract, mathematically balance, and audit complex tax invoices (Sales & Purchase) with the rigor of a Chartered Accountant.

## Key Features

- **Granular Line-Item Extraction:** Uses advanced LLMs (`gemini-2.5-flash` / `gpt-4o`) to intelligently parse highly unstructured and complex PDF tables, ignoring structural headers and capturing actual billed items perfectly.
- **Gross vs. Net Auto-Correction:** Dynamically detects LLM hallucinations where Gross amounts are mistakenly extracted instead of Net amounts, automatically netting them against discounts to mathematically balance the invoice.
- **Anti-Double Counting Guardrail:** Prevents duplicate line items by detecting when the AI erroneously extracts both the granular line items AND the "Sub Total" row.
- **Mathematical Tax Apportionment:** Automatically distributes overall invoice taxes (IGST, CGST, SGST) across distinct line items based on their individual net taxable values.
- **Automated Balancing:** If the AI misses a small item (like a late fee at the bottom of the page), the Python backend detects the discrepancy between the extracted lines and the "Final Total", automatically injecting an `Unallocated / Missing Lines` row so the final ledger balances perfectly to the penny.

## System Architecture

1. **OCR & LLM Extraction (`invoice_processor.py`):** Uses PyMuPDF (`fitz`) to extract raw text, which is parsed by an LLM via OpenRouter (`litellm`). The AI enforces strict Pydantic schemas and strict "CA Guardrails" in the prompt.
2. **Python Math Engine:** Before saving the data, the backend mathematically verifies that the sum of the line items equals the invoice's Final Total. Any discrepancies are automatically audited and scaled/corrected.
3. **Data Aggregation (`run_sales_extraction.py`):** Loops over incoming invoices, runs the auditing pipeline, deduplicates entries, and outputs a perfectly balanced, CA-ready `Sales_Output.xlsx` (or `Purchase_Output.xlsx`).

## Setup

1. Clone the repository.
2. Create a `.env` file based on `.env.example` and add your OpenRouter API key:
   ```env
   OPENROUTER_API_KEY="sk-or-v1-..."
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Place PDFs in the `salesinvoices/` or `purchaseinvoices/` directories.
5. Run the pipeline:
   ```bash
   python run_sales_extraction.py
   ```

## Scalability Roadmap

For high-volume production deployments (e.g., 10,000+ invoices/month), the sequential loop should be upgraded to asynchronous processing queues (like SQS/Celery) with database storage to handle high-throughput concurrency, fault tolerance, and API exponential backoff.
