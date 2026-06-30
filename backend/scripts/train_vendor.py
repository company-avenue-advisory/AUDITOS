"""
Vendor training script for Marquecom Agency LLP.
Runs all Marquecom invoices through the extraction pipeline and builds:
  1. backend/data/vendor_profiles/27ACDFM3235E1ZI_golden.json  — validated extraction results
  2. backend/data/vendor_profiles/27ACDFM3235E1ZI.json         — vendor profile with few-shot examples
"""
import sys, os, json, glob, re
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from invoice_processor import process_pdf

BASE_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INVOICE_DIR  = os.path.join(BASE_DIR, "..", "marquecom_invoices")
PROFILE_DIR  = os.path.join(BASE_DIR, "data", "vendor_profiles")
GOLDEN_FILE  = os.path.join(PROFILE_DIR, "27ACDFM3235E1ZI_golden.json")
PROFILE_FILE = os.path.join(PROFILE_DIR, "27ACDFM3235E1ZI.json")

VENDOR_GSTIN = "27ACDFM3235E1ZI"
VENDOR_NAME  = "MARQUECOM AGENCY LLP"

os.makedirs(PROFILE_DIR, exist_ok=True)

def is_export(items) -> bool:
    if not items:
        return False
    return any((item.get("gstr1_category") or "").upper() == "EXPORT" for item in items)

def collect_pdfs():
    pattern = os.path.join(INVOICE_DIR, "**", "*.pdf")
    return sorted(glob.glob(pattern, recursive=True))

def extract_one(pdf_path: str) -> dict:
    fname = os.path.basename(pdf_path)
    print(f"  Extracting: {fname} ...", end=" ", flush=True)
    try:
        res = process_pdf(pdf_path, invoice_type="sales")
        items = [
            {
                "particulars":        item.particulars,
                "hsn":                item.hsn,
                "taxable_value":      item.taxable_value,
                "cgst_amount":        item.cgst_amount,
                "sgst_amount":        item.sgst_amount,
                "igst_amount":        item.igst_amount,
                "total_invoice_value":item.total_invoice_value,
                "gstr1_category":     item.gstr1_category,
                "invoice_no":         item.invoice_no,
                "voucher_date":       item.voucher_date,
                "party_gstin":        item.party_gstin,
                "party_ledger_name":  item.party_ledger_name,
            }
            for item in res.sales_items
        ]
        entry = {
            "file":                pdf_path,
            "filename":            fname,
            "items_count":         len(items),
            "invoice_type":        "EXPORT" if is_export(items) else "DOMESTIC",
            "overall_taxable":     res.overall_taxable_value,
            "overall_cgst":        res.overall_cgst_amount,
            "overall_sgst":        res.overall_sgst_amount,
            "overall_igst":        res.overall_igst_amount,
            "overall_total":       res.overall_total_invoice_value,
            "items":               items,
        }
        print(f"OK  ({len(items)} items, {entry['invoice_type']})")
        return entry
    except Exception as e:
        print(f"ERROR: {e}")
        return {"file": pdf_path, "filename": fname, "error": str(e), "items": []}

def pick_few_shot_examples(golden: list) -> list:
    examples = []
    seen_types = set()

    for entry in golden:
        if entry.get("error") or not entry["items"]:
            continue
        inv_type = entry["invoice_type"]
        if inv_type in seen_types:
            continue

        item = entry["items"][0]
        cat  = (item.get("gstr1_category") or "").upper()
        key  = f"{inv_type}_{cat}"
        if key in seen_types:
            continue
        seen_types.add(key)
        seen_types.add(inv_type)

        examples.append({
            "invoice_type": f"{inv_type.lower()}_{cat.lower()}",
            "filename":     entry["filename"],
            "output": {
                "particulars":        item["particulars"],
                "taxable_value":      item["taxable_value"],
                "cgst_amount":        item["cgst_amount"],
                "sgst_amount":        item["sgst_amount"],
                "igst_amount":        item["igst_amount"],
                "total_invoice_value":item["total_invoice_value"],
                "hsn":                item["hsn"],
                "gstr1_category":     item["gstr1_category"],
            }
        })
        if len(examples) >= 4:
            break
    return examples

def build_profile(golden: list, examples: list) -> dict:
    sac_codes = set()
    currencies_seen = set()
    for entry in golden:
        for item in entry.get("items", []):
            if item.get("hsn"):
                sac_codes.add(str(item["hsn"]))
        # Guess currency from filename
        fname = entry.get("filename", "")
        if re.search(r'(FR|DE|BE)', fname.upper()):
            currencies_seen.add("EUR")
        elif re.search(r'US', fname.upper()):
            currencies_seen.add("USD")
        else:
            currencies_seen.add("INR")

    return {
        "gstin":                  VENDOR_GSTIN,
        "name":                   VENDOR_NAME,
        "invoice_number_prefix":  "MARQ-",
        "decimal_format":         "european_when_foreign_currency",
        "sac_codes":              sorted(sac_codes),
        "currencies":             sorted(currencies_seen),
        "export_rule":            "lut_zero_rated",
        "domestic_tax_rate":      18,
        "gstr1_categories": {
            "domestic_with_gstin":  "B2B",
            "domestic_without_gstin": "B2CS",
            "foreign_buyer":        "EXPORT",
        },
        "prompt_hints": [
            f"KNOWN VENDOR: {VENDOR_NAME} (GSTIN {VENDOR_GSTIN})",
            "European decimal format in EUR/USD invoices: '1.200,00' = 1200.00, '4.200,00' = 4200.00 (period=thousands, comma=decimal)",
            "If invoice says 'EXPORT INVOICE', 'LUT', 'Letter of Undertaking', or Place of Supply is a foreign country → gstr1_category=EXPORT, cgst=0, sgst=0, igst=0",
            f"SAC codes used: {', '.join(sorted(sac_codes))} — 998316=design/branding, 998313=web dev, 998314=SEO/digital, 9971=misc",
            "Domestic invoices (INR): CGST+SGST at 18% (9% each); B2B if buyer has GSTIN, B2CS if no GSTIN",
        ],
        "few_shot_examples":      examples,
        "trained_at":             datetime.utcnow().isoformat() + "Z",
        "invoice_count":          len([e for e in golden if not e.get("error")]),
    }

def main():
    pdfs = collect_pdfs()
    print(f"\nFound {len(pdfs)} Marquecom invoices\n{'='*60}")

    golden = []
    for pdf_path in pdfs:
        entry = extract_one(pdf_path)
        golden.append(entry)

    # Save golden dataset
    with open(GOLDEN_FILE, "w", encoding="utf-8") as f:
        json.dump(golden, f, indent=2, ensure_ascii=False)

    ok = [e for e in golden if not e.get("error")]
    errors = [e for e in golden if e.get("error")]
    domestic = [e for e in ok if e["invoice_type"] == "DOMESTIC"]
    exports  = [e for e in ok if e["invoice_type"] == "EXPORT"]

    print(f"\n{'='*60}")
    print(f"Results: {len(ok)} OK  |  {len(errors)} errors")
    print(f"  Domestic: {len(domestic)}  |  Export: {len(exports)}")

    if errors:
        print("\nFailed invoices:")
        for e in errors:
            print(f"  ✗ {e['filename']}: {e['error']}")

    # Build and save vendor profile
    examples = pick_few_shot_examples(golden)
    profile  = build_profile(golden, examples)

    with open(PROFILE_FILE, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2, ensure_ascii=False)

    print(f"\nGolden dataset → {GOLDEN_FILE}")
    print(f"Vendor profile  → {PROFILE_FILE}")
    print(f"\nFew-shot examples selected ({len(examples)}):")
    for ex in examples:
        print(f"  [{ex['invoice_type']}] {ex['filename']} — {ex['output']['particulars'][:50]}")

if __name__ == "__main__":
    main()
