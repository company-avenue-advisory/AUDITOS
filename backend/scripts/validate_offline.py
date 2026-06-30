"""
Offline validator for One Stack Solution invoices.
Replays post-processing (math_verification_agent, interstate detection) on
already-cached LLM extractions stored in 06AAGCR4375J2Z1_golden.json.
No API calls — zero token cost.
"""
import sys, os, json, re
sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from invoice_processor import (
    SuvitSalesItem, math_verification_agent, qc_audit_sales_items,
    remove_subtotals, _correct_taxable_values,
)

BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLDEN_FILE = os.path.join(BASE_DIR, "data", "vendor_profiles", "06AAGCR4375J2Z1_golden.json")
TOLERANCE   = 2.0

def ok(got, exp, tol=TOLERANCE):
    try:
        return abs(float(got or 0) - float(exp or 0)) <= tol
    except:
        return str(got).strip().lower() == str(exp).strip().lower()

def main():
    with open(GOLDEN_FILE, encoding='utf-8') as f:
        data = json.load(f)

    results = data['results']
    passed = failed = 0
    field_pass = {k: 0 for k in ['taxable','cgst','sgst','igst','total']}
    field_total = 0

    print(f"\nOffline replay — {len(results)} invoices (no API calls)\n{'='*65}")

    for r in results:
        ref = r['ref']
        g   = r['golden']
        ext = r.get('extracted', {})
        raw_items = ext.get('items', [])

        if not raw_items:
            print(f"  [{ref}] no cached items — skip")
            continue

        # Rebuild SuvitSalesItem objects from cached extraction
        party_gstin = g['gstin']
        items = []
        for it in raw_items:
            si = SuvitSalesItem(
                particulars         = it.get('particulars',''),
                taxable_value       = it.get('taxable', 0.0),
                cgst_amount         = it.get('cgst', 0.0),
                sgst_amount         = it.get('sgst', 0.0),
                igst_amount         = it.get('igst', 0.0),
                total_invoice_value = it.get('total', 0.0),
                hsn                 = it.get('hsn', ''),
                gstr1_category      = None,   # force re-classification (ignore buggy EXPORT)
                party_gstin         = party_gstin,
                place_of_supply     = '',
            )
            items.append(si)

        # Replicate the new tax-amount-based interstate detection:
        # Primary signal = invoice's own printed tax columns (stored in golden).
        # These are the overall amounts extracted by _extract_gst_summary_table.
        # The golden JSON stores what the modular pipeline extracted overall.
        g_cgst = g['cgst']
        g_sgst = g['sgst']
        g_igst = g['igst']
        if g_igst > 0 and g_cgst == 0 and g_sgst == 0:
            is_interstate = True
            flag = "IGST (golden printed tax)"
        elif (g_cgst > 0 or g_sgst > 0) and g_igst == 0:
            is_interstate = False
            flag = "CGST+SGST (golden printed tax)"
        else:
            # Ambiguous — fallback to buyer state vs fixed seller state
            buyer_state = party_gstin[:2] if len(party_gstin) >= 2 else ""
            seller_state = "27" if ref.startswith("MH") else "06"
            is_interstate = (buyer_state != seller_state) if buyer_state else None
            flag = f"AMBIGUOUS FALLBACK ({'IGST' if is_interstate else 'CGST+SGST'})"

        print(f"  [{ref}]  {flag}", end='  ', flush=True)

        # Re-run QC audit (reclassifies HSN and gstr1_category correctly)
        items = qc_audit_sales_items(items)

        # Re-run math verification with correct interstate flag
        items = math_verification_agent(items, is_interstate=is_interstate)

        # Aggregate
        ext_taxable = sum(i.taxable_value or 0 for i in items)
        ext_cgst    = sum(i.cgst_amount   or 0 for i in items)
        ext_sgst    = sum(i.sgst_amount   or 0 for i in items)
        ext_igst    = sum(i.igst_amount   or 0 for i in items)
        ext_total   = sum(i.total_invoice_value or 0 for i in items)

        # Golden expected total = taxable + taxes (not gross+taxes)
        g_total_clean = g['taxable'] + g['cgst'] + g['sgst'] + g['igst']

        checks = {
            'taxable': ok(ext_taxable, g['taxable']),
            'cgst':    ok(ext_cgst,    g['cgst']),
            'sgst':    ok(ext_sgst,    g['sgst']),
            'igst':    ok(ext_igst,    g['igst']),
            'total':   ok(ext_total,   g_total_clean),
        }
        all_ok = all(checks.values())
        if all_ok: passed += 1
        else:       failed += 1
        field_total += 1
        for k in field_pass:
            if checks[k]: field_pass[k] += 1

        fails = {}
        for k, v2 in [('taxable',ext_taxable),('cgst',ext_cgst),('sgst',ext_sgst),('igst',ext_igst)]:
            gv = g[k]
            if not checks[k]:
                fails[k] = f"{float(v2 or 0):.2f} vs {float(gv or 0):.2f}"
        if not checks['total']:
            fails['total'] = f"{ext_total:.2f} vs {g_total_clean:.2f}"

        tag = 'PASS' if all_ok else 'FAIL'
        print(f"{tag}" + (f"  DIFF: {fails}" if fails else ''))

    total = passed + failed
    print(f"\n{'='*65}")
    print(f"Predicted result after lut-fix: {passed}/{total} PASS ({100*passed//max(total,1)}%)")
    for field in ['taxable','cgst','sgst','igst','total']:
        p = field_pass[field]
        print(f"  {field:<10} {p}/{field_total}  ({100*p//max(field_total,1)}%)")

if __name__ == '__main__':
    main()
