"""
Regression tests for invoice_processor.extract_deterministic_line_items /
_extract_invoice_header - the canonical (regex, no LLM) OneStack sales
line-item extractor.

Each fixture is real invoice text pulled from actual OneStack invoices this
session, locking in bugs found and fixed against them:

  - Krushiseva: small intrastate invoice, late fee section has no HSN
  - Bijnor: single ad-hoc line invoice (no A-J section template at all) -
    this exact bug caused the invoice to be silently missing from an
    earlier manual pipeline run before extract_deterministic_line_items
    grew the single-line fallback.
  - Pragati: only 2 of 10 possible sections present, relettered A/B instead
    of their "canonical" I/J - the letter-agnostic [A-J] anchor exists
    specifically because of this invoice.
  - Muslim Co-op: Rs.50,000 advance must cascade onto the single largest
    section (Transactional Charges), not be spread proportionally across
    every section - the earlier bug here overstated 30 invoices' line-item
    taxable value by exactly the advance amount.

Each case is deterministic: no LLM, no I/O, no network.
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from backend.invoice_processor import (
    extract_deterministic_line_items, _extract_invoice_header, NOT_SPECIFIED_HSN,
)


def _sum(items, key):
    return round(sum(i[key] for i in items), 2)


class TestDeterministicLineItems(unittest.TestCase):

    def test_krushiseva_small_intrastate_with_late_fee(self):
        text = """A SAAS / Mobile Application / UPI QR 9971
Saas Mobile Model 1 - Rs. 5 per user - 0 to 1000 Users - RS: 5000 (per month)
1000 - 0 5,000.00
Additional Users 0 - 5 0.00
Discount on Application - 3,000.00
Sub Total 2,000.00
B Soundbox Charges 997319
Model 1 - Rs. 999 per device / Annual plan - 0.00
Model 2 - Rs. 149 per device / per month - 0.00
Sub Total 0.00
C CBS (Core Banking Solution)
D Transactional Messages 998599
SMS Login - 459 0.20 91.80
SMS Transactions - 2378 0.20 475.60
WhatsApp Transactions - 2378 0.00 0.00
App Notifications Transactions - 2378 0.00 0.00
Discount on Transactional Communication - - 100% - 567.40
Sub Total 0 0 0 0.00
E Promotional Messages 998599
Sub Total - 0 0.00
F KYC Charges 998529
PAN - 1 5.00 5.00
Sub Total 5.00
G Late Fees Charges 4774.00 18% 71.61
H Ad Hoc Charges
Net Cost 2,076.61
"""
        items = extract_deterministic_line_items(text, 76.61, 9, 9, 0)
        self.assertEqual(_sum(items, "taxable"), 76.61)
        self.assertEqual(_sum(items, "cgst"), 6.89)
        self.assertEqual(_sum(items, "sgst"), 6.89)
        self.assertEqual(_sum(items, "igst"), 0.0)
        # the Rs.2,000 SaaS section was entirely consumed by the advance and
        # correctly dropped, leaving only KYC + Late Fee
        labels = {i["particulars"] for i in items}
        self.assertNotIn("SaaS/UPI Platform Charges", labels)
        late_fee = [i for i in items if i["particulars"] == "Late Payment Fee"][0]
        self.assertEqual(late_fee["hsn"], NOT_SPECIFIED_HSN)

    def test_bijnor_single_line_invoice_no_section_template(self):
        text = """A
SoundBox Model 1 - Rs. 999 per
device / Annual plan
997319
16.00
999.00
15,984.00
B
Final Total
15,984.00
"""
        items = extract_deterministic_line_items(text, 15984.00, 0, 0, 18)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["hsn"], "997319")
        self.assertEqual(_sum(items, "taxable"), 15984.00)
        self.assertEqual(_sum(items, "igst"), 2877.12)

    def test_sirohi_single_line_invoice_different_wording(self):
        text = """A Dun & Bradstreet (DUNS)

Number Generation

998313 10,000.00 10,000.00

B Final Total 10,000.00
"""
        items = extract_deterministic_line_items(text, 10000.00, 0, 0, 18)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["hsn"], "998313")
        self.assertEqual(_sum(items, "taxable"), 10000.00)

    def test_pragati_relettered_sections_not_canonical_letters(self):
        # Only "Transactional Charges" (canonically I) and "UPI 2.0
        # Transactional Messages" (canonically J) are present on this
        # invoice - they get relettered A and B, not I and J.
        text = """A
Transactional Charges
Financial Transactions
0 15,807
0.5
7,903.50
Non-Financial Transactions
0 61,953
0.5
30,976.50
Total
-
-
38,880.00
B
UPI 2.0 Transactional Messages
998599
SMS Charges
- 16,389
0.20
3,277.80
Transactional Notification Charges
- 15,807
0.10
1,580.70
Sub Total
0
0
0
4,858.50
Net Cost
43,738.50
"""
        items = extract_deterministic_line_items(text, 43738.50, 0, 0, 18)
        self.assertEqual(_sum(items, "taxable"), 43738.50)
        self.assertEqual(_sum(items, "igst"), 7872.93)
        hsn_by_label = {i["particulars"]: i["hsn"] for i in items}
        self.assertEqual(hsn_by_label["High-Volume Transactional Charges"], NOT_SPECIFIED_HSN)
        self.assertEqual(hsn_by_label["UPI 2.0 Transactional Messaging Charges"], "998599")

    def test_muslim_coop_advance_cascades_onto_largest_section_only(self):
        text = """A SAAS / Mobile Application / UPI QR
9971
Standard Application Charges @5 Rs Per User
0
-
0
0.00
Additional Users
1079
-
5
5,395.00
Sub Total
5,395.00
B Soundbox Charges
997319
SoundBox Model 1 - Rs. 999 per device / Annual
plan
-
0.00
SoundBox Model 2 - Rs. 149 per device / per
month
-
0.00
Sub Total
0.00
C CBS (Core Banking Solution)
D Transactional Messages
998599
SMS Login
-
1608
0.20
321.60
SMS Transactions
-
7143
0.20
1,428.60
WhatsApp Transactions
-
7143
0.00
0.00
App Notifications Transactions
-
7143
0.10
714.30
Sub Total
0
0
0
2,464.50
E Promotional Messages
998599
SMS
152494
5
0
0.00
WhatsApp Message
152494
5
0
0.00
App Notification
623
5
0
0.00
Sub Total
-
0
0
0.00
F
KYC Charges
998529
PAN
-
2
5.00
10.00
AADHAAR
-
0
5.00
0.00
GST
-
0
5.00
0.00
CIN
-
0
0
0
Sub Total
10.00
G
Late Fees Charges
85898.00
18%
1288.47
H
Ad Hoc Charges
I
Transactional Charges
Financial Transactions
0
19,80,066
0.25
4,95,016.50
Non-Financial Transactions
0
33,22,607
0.25
8,30,651.75
Total
-
-
13,25,668.25
J
UPI 2.0 Transactional Messages
998599
Transactional SMS Charges
-
19,80,066
0.20
3,96,013.20
SMS OTP Charges
-
1,159
0.20
231.80
Sub Total
0
0
0
3,96,245.00
Net Cost
17,31,071.22
"""
        # Rs.17,31,071.22 net cost minus Rs.50,000 advance = Rs.16,81,071.22 taxable
        items = extract_deterministic_line_items(text, 1681071.22, 9, 9, 0)
        self.assertEqual(_sum(items, "taxable"), 1681071.22)
        self.assertEqual(_sum(items, "cgst"), 151296.41)
        self.assertEqual(_sum(items, "sgst"), 151296.41)

        # the advance must come entirely off the largest pre-advance section
        # (Transactional Charges, Rs.13,25,668.25) - not spread proportionally
        # across every section, which would incorrectly touch KYC/Late Fee too
        transactional = [i for i in items if i["particulars"] == "High-Volume Transactional Charges"][0]
        self.assertEqual(transactional["taxable"], 1275668.25)
        kyc = [i for i in items if i["particulars"] == "KYC Verification Charges"][0]
        self.assertEqual(kyc["taxable"], 10.00)

    def test_no_section_and_no_single_line_match_returns_empty(self):
        # not a recognized OneStack template at all - must fall back to
        # whatever the caller's LLM path extracted, not force a wrong result
        items = extract_deterministic_line_items("completely unrelated text", 100.0, 9, 9, 0)
        self.assertEqual(items, [])

    def test_invoice_header_parses_party_gstin_invoice_no_date(self):
        text = """Customer Name:
THE BIJNOR URBAN COOPERATIVE BANK LTD
Billing Month:
June 2026
GSTIN:
09AAAAT1031B1Z6
Invoice Number: OHR26061001
PAN:
AAAAT1031B
Date of Invoice:
01-06-2026
"""
        header = _extract_invoice_header(text)
        self.assertEqual(header["party_name"], "THE BIJNOR URBAN COOPERATIVE BANK LTD")
        self.assertEqual(header["party_gstin"], "09AAAAT1031B1Z6")
        self.assertEqual(header["invoice_no"], "OHR26061001")
        self.assertEqual(header["voucher_date"], "01-06-2026")
        self.assertEqual(header["place_of_supply"], "UTTAR PRADESH")


if __name__ == "__main__":
    unittest.main()
