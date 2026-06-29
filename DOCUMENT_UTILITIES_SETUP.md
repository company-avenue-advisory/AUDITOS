# Document Utilities System — Complete Setup Guide

## ✅ Status
**PRODUCTION-READY** — All 5 tools tested and validated.

---

## 📋 What You Have

### 5 Specialized Tools for GST/Tax Compliance

1. **Bank Statement Parser** — Extract transactions from any Indian bank PDF
2. **OCR Extractor** — Convert scanned PDFs to searchable text
3. **Scan Enhancer** — Improve scanned document quality
4. **Portal Splitter** — Split large PDFs into upload-sized chunks
5. **PDF Compressor** — Reduce file size losslessly

**All tools work offline. Zero external API calls. $0 monthly cost.**

---

## 🚀 Quick Start (5 minutes)

### Step 1: Install Dependencies

```bash
# Navigate to project
cd /path/to/antigravityaudit

# Install required packages
pip install numpy opencv-python-headless pillow

# Verify installation
python backend/test_document_utilities.py
```

Expected output:
```
✅ All 5 Document Utilities tools tested
SYSTEM STATUS: ✅ PRODUCTION-READY
```

### Step 2: Start the Backend Server

```bash
# Terminal 1: Backend
cd /path/to/antigravityaudit
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Expected output:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Step 3: Start the Frontend Development Server

```bash
# Terminal 2: Frontend
cd /path/to/antigravityaudit/frontend
npm install  # (if not already done)
npm run dev
```

Expected output:
```
Ready in 2.5s.
Local:        http://localhost:3000
```

### Step 4: Access the Application

Open browser: **http://localhost:3000**

Navigate to: **Document Utilities** (left sidebar)

---

## 🧪 Testing All 5 Tools

### Tab 1: Bank Statement Locker

**Test with**: Any Indian bank PDF statement

**Expected**:
- Extracts transaction date, narration, debit, credit, balance
- Shows confidence badges (green=SURE, yellow=PROBABLE)
- Displays count: "Extracted X transactions. SURE: X, PROBABLE: X, UNCERTAIN: X"

**If encrypted**: Enter bank PDF password

---

### Tab 2: Portal Splitter

**Test with**: Large PDF file (>10MB)

**Configuration**: Set target size to 4.5 MB

**Expected**:
- Creates ZIP file with sub-5MB chunks
- Downloads as `filename_split.zip`
- Shows chunk count and file sizes

---

### Tab 3: Scan Enhancer

**Test with**: Scanned image (JPG, PNG) of a document

**Expected**:
- Converts to greyscale
- Improves contrast
- Downloads clean PDF with better text clarity

**Note**: Requires OpenCV. If not installed, falls back to PIL (simpler enhancement).

---

### Tab 4: PDF Compressor

**Test with**: Any PDF file

**Configuration**: Quality slider (0-100)

**Expected**:
- Shows original and compressed sizes
- Calculates compression ratio
- Downloads optimized PDF

---

### Tab 5: OCR Extractor

**Test with**: Scanned PDF (no searchable text)

**Configuration**: Select OCR provider:
- **Auto** (recommended) — tries PyMuPDF → Tesseract → EasyOCR
- **PyMuPDF** — instant (native text layer)
- **Tesseract** — ~1-2s per page (if available)
- **EasyOCR** — best accuracy, ~30-60s

**Expected**:
- Extracts all visible text
- Shows provider used
- Displays character count

---

## 🔧 Advanced Configuration

### Enable Tesseract (Optional)

For better OCR on scanned PDFs:

**Linux/Mac**:
```bash
brew install tesseract  # macOS
sudo apt-get install tesseract-ocr  # Ubuntu
pip install pytesseract
```

**Windows**:
1. Download installer: https://github.com/UB-Mannheim/tesseract/wiki
2. Install to default location
3. Run: `pip install pytesseract`

### Enable EasyOCR (Optional)

For best accuracy (slower, ~250MB download):

```bash
pip install easyocr
```

First run will download model (~250MB). Subsequent runs use cached model.

---

## 📊 API Endpoints Reference

All endpoints at: `http://localhost:8000/api/docs`

### Document Utilities Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/docs/bank-parse` | POST | Parse bank statements |
| `/api/docs/split-portal` | POST | Split PDF by size |
| `/api/docs/enhance-scan` | POST | Enhance scanned images |
| `/api/docs/compress` | POST | Compress PDF |
| `/api/invoice-metadata` | POST | Extract text via OCR |

### Example: Bank Statement Parsing

```bash
curl -X POST "http://localhost:8000/api/docs/bank-parse" \
  -F "file=@statement.pdf" \
  -F "password=" \
  -F "confidence_min="
```

Response:
```json
{
  "success": true,
  "transactions": [
    {
      "date": "01-Jan-2024",
      "narration": "NEFT Transfer",
      "debit": "10000",
      "credit": "",
      "balance": "50000",
      "confidence": "SURE",
      "bank_detected": "HDFC",
      "extraction_method": "table"
    }
  ],
  "summary": {
    "total": 45,
    "sure": 44,
    "probable": 1,
    "uncertain": 0
  }
}
```

---

## ⚙️ Environment Variables

Create `.env` file in `backend/` directory:

```bash
# Database (optional, for production)
DATABASE_URL=postgresql://user:pass@localhost/auditos

# API Keys (optional, for additional features)
GEMINI_API_KEY=your_key_here
GROQ_API_KEY=your_key_here

# Document Processing
FIRM_GSTIN=06XXXXXXXXXXXXX  # Your firm's GSTIN (for GST routing)

# Security
JWT_SECRET_KEY=your-secret-key-here

# CORS (optional)
ALLOWED_ORIGINS=http://localhost:3000,https://yourdomain.com
```

**Note**: Most defaults work without env vars. Only customize if deploying to production.

---

## 🔍 Troubleshooting

### Issue: "OpenCV not installed"

**Solution**:
```bash
pip install opencv-python-headless
```

The system will automatically fall back to PIL if cv2 unavailable, but cv2 is preferred.

---

### Issue: "pytesseract module not found"

**Solution**: Either skip (OCR will try EasyOCR) or:
```bash
pip install pytesseract
# Then install tesseract-ocr on your system (see Advanced Configuration)
```

---

### Issue: "No transactions extracted from bank PDF"

**Possible causes**:
1. **Scanned PDF** — Use OCR Extractor instead
2. **Different bank format** — Try regex fallback (happens automatically)
3. **Password protected** — Enter password in dialog
4. **Corrupted file** — Try re-exporting from bank portal

**Debug**: Check backend console for extraction logs showing which method was used.

---

### Issue: "OCR is very slow"

**Solution**: Use specific provider instead of auto:
- Try **PyMuPDF** first (instant)
- If no text, try **Tesseract** (~1-2s)
- Only use **EasyOCR** if absolutely needed

---

## 📈 Performance Tuning

### For 1000+ PDFs per day:

1. **Disable auto-fallback** — select PyMuPDF for native PDFs
2. **Pre-enhance scanned PDFs** — use Scan Enhancer tab first
3. **Batch processing** — process multiple files in parallel (implement in calling service)
4. **Cache models** — EasyOCR caches after first download

---

## 🔐 Security Notes

- ✅ All processing is **local** — no data sent to cloud
- ✅ Password-protected PDFs require password to decrypt
- ✅ Input validation prevents oversized file uploads (50MB cap)
- ✅ No API keys stored in code (use environment variables)
- ✅ Error messages don't leak sensitive info

---

## 📝 Logging & Monitoring

### View extraction logs:

Backend console shows:
```
[Bank Detection] HDFC (confidence: 0.95)
[Stage 2] Attempting table extraction...
  Extracted 45 transactions from 1 table(s)
[Confidence Filter] 45 → 45 (min: None)
[Performance] Extracted 45 transactions in 1.23s
```

### Track performance:

- Response times in API responses (headers: `X-Extraction-Time`)
- Confidence distribution in summary stats
- Provider used in OCR results

---

## 🚀 Production Deployment

### Docker Deployment

```dockerfile
FROM python:3.10

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install -r requirements.txt

COPY backend/ .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Build and run:
```bash
docker build -t audit-os-document-utils .
docker run -p 8000:8000 audit-os-document-utils
```

### Gunicorn (Production ASGI)

```bash
pip install gunicorn
gunicorn backend.main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker
```

### Nginx Reverse Proxy

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location /api/ {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location / {
        proxy_pass http://localhost:3000;
    }
}
```

---

## 📞 Support

### Test Suite

Run anytime to verify system health:
```bash
python backend/test_document_utilities.py
```

All tests passing = system is working correctly.

### API Documentation

Interactive API docs available at:
```
http://localhost:8000/docs
```

### Error Messages

The system provides clear error messages with recovery hints. Check:
1. Browser console (frontend errors)
2. Backend terminal (extraction logs)
3. Network tab (API response errors)

---

## ✅ Final Checklist

Before going live:

- [ ] Dependencies installed (`pip install numpy opencv-python-headless pillow`)
- [ ] Tests pass (`python backend/test_document_utilities.py`)
- [ ] Backend starts without errors
- [ ] Frontend loads at http://localhost:3000
- [ ] Document Utilities sidebar tab visible
- [ ] All 5 tabs load without errors
- [ ] Bank Statement tab accepts PDF upload
- [ ] At least one tool tested successfully
- [ ] Error handling works (try invalid file)
- [ ] No console errors in browser dev tools

**Once checklist passes, you're ready for production! 🚀**

---

## 📚 File Manifest

Core files (don't modify unless you know what you're doing):
```
backend/
  services/document_core.py          # All 5 tools implementation
  main.py                            # API endpoints
  requirements.txt                   # Dependencies
  test_document_utilities.py         # Harness test suite
frontend/
  src/app/document-utilities/page.tsx # UI for all 5 tools
DOCUMENT_UTILITIES_SETUP.md          # This file
```

---

**System Status: ✅ PRODUCTION-READY**

Last updated: 2026-06-29  
Tested on: Python 3.10+, Node.js 18+, Windows/Linux/macOS
