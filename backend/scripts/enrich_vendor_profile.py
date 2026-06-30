"""
Post-processes the golden dataset to produce an enriched vendor profile:
- Picks 4 diverse few-shot examples (domestic B2B, domestic B2CS, export EUR multi, export USD)
- Adds known_customers map (buyer name → GSTIN) for prompt injection
- Adds invoice_patterns summary for layout hints
- Writes updated backend/data/vendor_profiles/27ACDFM3235E1ZI.json
"""
import sys, os, json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE_DIR  = os.path.join(BASE_DIR, "data", "vendor_profiles")
GOLDEN_FILE  = os.path.join(PROFILE_DIR, "27ACDFM3235E1ZI_golden.json")
PROFILE_FILE = os.path.join(PROFILE_DIR, "27ACDFM3235E1ZI.json")

with open(GOLDEN_FILE, encoding="utf-8") as f:
    golden = json.load(f)

with open(PROFILE_FILE, encoding="utf-8") as f:
    profile = json.load(f)

# ── 1. Build known_customers map ─────────────────────────────────────────────
known_customers: dict[str, str] = {}
for entry in golden:
    for item in entry.get("items", []):
        name  = (item.get("party_ledger_name") or "").strip().rstrip(",")
        gstin = (item.get("party_gstin") or "").strip()
        if name and gstin and gstin.lower() not in ("null", "none"):
            known_customers[name] = gstin

print("Known customers:")
for name, gstin in sorted(known_customers.items()):
    print(f"  {name:<40} {gstin}")

# ── 2. Pick 4 diverse few-shot examples ─────────────────────────────────────
#   Slot 1: Domestic B2B, single item
#   Slot 2: Domestic B2B, multi-item (to show multi-line extraction)
#   Slot 3: Export EUR, multi-item (to show European decimal + 0 tax + multiple lines)
#   Slot 4: Export USD, single item (to show USD amount as-is)

def make_example(inv_type: str, entry: dict, item_idx=None) -> dict:
    items = entry["items"]
    if item_idx is not None:
        sample = items[item_idx]
    else:
        sample = items[0]
    return {
        "invoice_type": inv_type,
        "filename": entry["filename"],
        "items_count": len(items),
        "output": {
            "particulars":        sample["particulars"],
            "hsn":                sample["hsn"],
            "taxable_value":      sample["taxable_value"],
            "cgst_amount":        sample["cgst_amount"],
            "sgst_amount":        sample["sgst_amount"],
            "igst_amount":        sample["igst_amount"],
            "total_invoice_value":sample["total_invoice_value"],
            "gstr1_category":     sample["gstr1_category"],
        }
    }

# Slot 1: MARQ-2025-07001 — domestic B2B, 1 item (Fitstatic website dev, ₹85k)
slot1 = next(e for e in golden if e["filename"] == "MARQ-2025-07001.pdf")

# Slot 2: MARQ-2025-09001 — domestic B2B, 2 items (Part 3 Fitstatic + Extra Hours)
slot2 = next(e for e in golden if e["filename"] == "MARQ-2025-09001.pdf")

# Slot 3: Marquecom_Invoice_2026_FR004 — export EUR, 3 items (European multi-line)
slot3 = next(e for e in golden if e["filename"] == "Marquecom_Invoice_2026_FR004.pdf")

# Slot 4: Marquecom_Invoice_2026_US003 — export USD, 1 item (Website Retainer $600)
slot4 = next(e for e in golden if e["filename"] == "Marquecom_Invoice_2026_US003.pdf")

few_shot = [
    make_example("domestic_b2b_single_item", slot1),
    make_example("domestic_b2b_multi_item",  slot2),
    make_example("export_eur_multi_item",     slot3),
    make_example("export_usd_single_item",    slot4),
]

print("\nFew-shot examples selected:")
for ex in few_shot:
    print(f"  [{ex['invoice_type']}] {ex['filename']} ({ex['items_count']} items) — {ex['output']['particulars'][:55]}")

# ── 3. Build invoice_patterns summary ────────────────────────────────────────
domestic = [e for e in golden if e["invoice_type"] == "DOMESTIC"]
exports  = [e for e in golden if e["invoice_type"] == "EXPORT"]

sac_codes = set()
for e in golden:
    for it in e.get("items", []):
        if it.get("hsn"):
            sac_codes.add(str(it["hsn"]))

invoice_patterns = {
    "domestic_invoice_prefix":  "MARQ-YYYY-NNNNN",
    "export_invoice_prefix":    "Marquecom_Invoice_YYYY_CCNNN",
    "domestic_count":           len(domestic),
    "export_count":             len(exports),
    "domestic_tax_rate_pct":    18,
    "domestic_split":           "CGST 9% + SGST 9%",
    "export_tax":               "0 (LUT zero-rated, no CGST/SGST/IGST)",
    "currencies": {
        "INR": "domestic invoices",
        "EUR": "France (FR), Germany (DE), Belgium (BE)",
        "USD": "USA (US)",
    },
    "european_decimal_note":    "EUR invoices use '1.200,00' = 1200.00 (period=thousands, comma=decimal)"
}

# ── 4. Update prompt_hints with known_customers ───────────────────────────────
customer_hint = "Known buyers (buyer name → GSTIN): " + "; ".join(
    f"{name}={gstin}" for name, gstin in sorted(known_customers.items())
)

prompt_hints = [
    f"KNOWN VENDOR: MARQUECOM AGENCY LLP (GSTIN {profile['gstin']})",
    "European decimal format in EUR/USD invoices: '1.200,00' = 1200.00, '4.200,00' = 4200.00 (period=thousands, comma=decimal)",
    "If invoice says 'EXPORT INVOICE', 'LUT', 'Letter of Undertaking', or Place of Supply is a foreign country → gstr1_category=EXPORT, cgst=0, sgst=0, igst=0",
    f"SAC codes used: {', '.join(sorted(sac_codes))} — 998316=design/branding, 998313=web dev, 999613=video editing, 9971=misc, 998311=marketing",
    "Domestic invoices (INR): CGST+SGST at 18% (9% each); B2B if buyer has GSTIN, B2CS if no GSTIN",
    customer_hint,
]

# ── 5. Write enriched profile ─────────────────────────────────────────────────
profile.update({
    "prompt_hints":       prompt_hints,
    "few_shot_examples":  few_shot,
    "known_customers":    known_customers,
    "invoice_patterns":   invoice_patterns,
    "sac_codes":          sorted(sac_codes),
    "invoice_count":      len(golden),
    "trained_at":         datetime.now().isoformat() + "Z",
})

with open(PROFILE_FILE, "w", encoding="utf-8") as f:
    json.dump(profile, f, indent=2, ensure_ascii=False)

print(f"\nEnriched profile written → {PROFILE_FILE}")
print(f"  {len(few_shot)} few-shot examples")
print(f"  {len(known_customers)} known customers")
print(f"  {len(sac_codes)} SAC codes")
