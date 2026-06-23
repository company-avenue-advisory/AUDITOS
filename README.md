# 📄 AI Invoice Extractor & GSTR-2B Reconciler

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https://github.com/Yugshri/invoiceextractor&env=NEXT_PUBLIC_API_URL)

A full-stack AI-powered application designed to automate the extraction of data from PDF invoices and seamlessly reconcile them against GSTR-2B JSON data downloaded from the GST portal.

## 🌟 Features

- **🧠 Intelligent Invoice Extraction**: Uses advanced LLMs to extract structured line-items from complex, multi-page PDF invoices.
- **⚡ Smart Model Routing**:
  - **OpenRouter (Cloud)**: Utilizes Llama 3.3 70B or Google's Gemini 2.5 Flash for blazing-fast extraction on standard documents.
  - **Local Ollama (On-Device)**: Fully private extraction using local models, perfect for large batch jobs or highly confidential documents.
- **📊 GSTR-2B Reconciliation**: Upload your GSTR-2B JSON file and reconcile it directly against extracted invoice data.
- **✅ Math & Validation Checks**: Built-in validation checks flag GSTIN length errors, missing mandatory fields, and mismatched totals.
- **📥 Excel Exports**:
  - Export extracted invoice data to cleanly formatted Excel files.
  - Generate comprehensive, color-coded reconciliation reports (Matched, Mismatched, Missing in 2B, Not Booked).

## 🛠️ Technology Stack

- **Backend**: Python 3, FastAPI, Pandas, OpenPyXL, Uvicorn, Pydantic
- **Frontend**: Next.js 16, React 19, Tailwind CSS v4, Lucide React
- **AI/LLM**: OpenRouter API, Local Ollama

---

## 🚀 Getting Started

Follow these steps to run the project locally.

### 1. Clone the repository
```bash
git clone https://github.com/Yugshri/invoiceextractor.git
cd invoiceextractor
```

### 2. Backend Setup
Navigate to the `backend` directory and set up the Python environment:

```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows use `venv\Scripts\activate`

# Install dependencies
pip install -r requirements.txt

# Start the FastAPI server
python main.py
```
The backend will run on `http://localhost:8000`.

*Note: Ensure you have your `OPENROUTER_API_KEY` set in a `.env` file if you plan to use cloud models. If using Ollama, ensure the Ollama service is running locally.*

### 3. Frontend Setup
Open a new terminal, navigate to the `frontend` directory, and start the development server:

```bash
cd frontend

# Install dependencies
npm install

# Start the Next.js dev server
npm run dev
```
The frontend will run on `http://localhost:3000`.

---

## 📖 How It Works

1. **Upload Invoices**: Drag and drop your PDF invoices into the web interface.
2. **Select Model**: Choose between OpenRouter Cloud models (Llama/Gemini) or Local Ollama.
3. **Review Data**: The system processes the PDFs and displays the extracted line items, automatically flagging any math discrepancies or missing fields.
4. **Reconcile (Optional)**: Upload your GSTR-2B JSON file. The system will match your books against the portal data.
5. **Export**: Download the final data or reconciliation report as an Excel spreadsheet.

---

## 🤝 Contributing
Contributions, issues, and feature requests are welcome!

## 📝 License
This project is licensed under the MIT License.
