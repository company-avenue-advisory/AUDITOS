"""
Fresh test: run 10 cooperative bank invoices (not in training set) through process_pdf()
and show the raw extracted output. No golden comparison — just see what the system produces.
"""
import sys, os, glob
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from invoice_processor import process_pdf

SALES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "salesinvoices")

# 10 cooperative bank invoices — diverse mix of IGST/CGST+SGST, sizes, with/without discount
TEST_FILES = [
    "MAMASAHEB__PAWAR__SATYAVIJAY_COOPERATIVE__BANK_KUNDAL-05-2026.pdf",   # MH26051045 CGST large
    "Nagar_Sahkari_Bank_Ltd._Gorakhpur-05-2026.pdf",                        # HR26051013 IGST tiny
    "Omerga_Janata_Sahakari_Bank_Ltd-05-2026.pdf",                          # MH26051055 CGST mid
    "Pravara_Sahakari_Bank_Ltd-05-2026.pdf",                                # MH26051061 CGST large
    "SHIVAJI_NAGARI_SAHAKARI_BANK_LIMITED_PAITHAN-05-2026.pdf",             # MH26051079 CGST very large
    "SHREE VIRPUR URBAN SAHAKARI BANK LTD.pdf",                             # MH26051085 IGST large
    "Sadalga_Urban_Souharda_Sahakari_Bank_Niyamit_Sadalga-05-2026.pdf",    # MH26051066 IGST tiny
    "Shiva_Sahakari_Bank_Niyamitha_Tarikere-05-2026.pdf",                   # MH26051078 IGST small
    "Shree_Basaveshwar_Urban_Co_operative_Bank_Ltd._Ranebennur-05-2026.pdf",# MH26051082 IGST small
    "Sind_CoOperative_Urban_Bank_Ltd.-05-2026.pdf",                         # MH26051093 IGST mid
]

def fmt(v):
    return f"{float(v or 0):>12,.2f}" if v is not None else f"{'0.00':>12}"

def main():
    print(f"\n{'='*70}")
    print(f"  FRESH TEST — 10 Cooperative Bank Invoices")
    print(f"{'='*70}")
    print(f"{'File':<45} {'#':>2}  {'Taxable':>12}  {'CGST':>10}  {'SGST':>10}  {'IGST':>10}  {'Total':>12}")
    print(f"{'-'*70}")

    passed = 0
    for fname in TEST_FILES:
        pdf_path = os.path.join(SALES_DIR, fname)
        if not os.path.exists(pdf_path):
            print(f"  NOT FOUND: {fname}")
            continue

        short = fname[:43]
        try:
            res = process_pdf(pdf_path, invoice_type='sales')
            items = res.sales_items or []

            ext_taxable = sum(i.taxable_value or 0 for i in items) or res.overall_taxable_value or 0
            ext_cgst    = sum(i.cgst_amount   or 0 for i in items) or res.overall_cgst_amount   or 0
            ext_sgst    = sum(i.sgst_amount   or 0 for i in items) or res.overall_sgst_amount   or 0
            ext_igst    = sum(i.igst_amount   or 0 for i in items) or res.overall_igst_amount   or 0
            ext_total   = sum(
                (i.taxable_value or 0) + (i.discount or 0) +
                (i.cgst_amount or 0) + (i.sgst_amount or 0) + (i.igst_amount or 0)
                for i in items
            ) or res.overall_total_invoice_value or 0

            # Quick sanity: taxes > 0 and total > taxable
            ok = (ext_cgst + ext_sgst + ext_igst) > 0 and ext_total >= ext_taxable
            tag = "OK " if ok else "???"
            passed += 1 if ok else 0

            print(f"\n[{tag}] {short}")
            print(f"       {len(items)} items | taxable={fmt(ext_taxable)}  cgst={fmt(ext_cgst)}  sgst={fmt(ext_sgst)}  igst={fmt(ext_igst)}  total={fmt(ext_total)}")
            for i in items:
                disc = f"  disc={i.discount:.2f}" if (i.discount or 0) > 0 else ""
                print(f"         [{i.hsn}] {str(i.particulars or '')[:50]:<50}  tax={fmt(i.taxable_value)}{disc}  igst={fmt(i.igst_amount)}  cgst={fmt(i.cgst_amount)}")

        except Exception as e:
            print(f"\n[ERR] {short}")
            print(f"       Error: {e}")

    print(f"\n{'='*70}")
    print(f"  Sanity-OK: {passed}/{len(TEST_FILES)}")
    print(f"{'='*70}\n")

if __name__ == '__main__':
    main()
