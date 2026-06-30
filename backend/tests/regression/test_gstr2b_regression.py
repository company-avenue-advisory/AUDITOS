"""
Regression tests for the GSTR-2B reconciliation engine.

Tests cover:
  - parse_gstr2b: both Shape A (portal) and Shape B (simplified) JSON formats
  - normalize_gstin / normalize_inv: all non-alphanumeric stripping rules
  - reconcile: matched / mismatch / missing_in_2b / not_in_books statuses
  - ₹2 tolerance boundary conditions
  - Multi-line-item aggregation before matching
  - Summary counts in reconcile() output

No LLM calls, no DB, no file I/O beyond the fixture loaded at module level.
"""
import sys
import os
import json
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from backend.services.gstr2b_reconciler import (
    parse_gstr2b,
    normalize_gstin,
    normalize_inv,
    reconcile,
    safe_float,
    AMOUNT_TOLERANCE,
)

# ── Fixture path ──────────────────────────────────────────────────────────────

_FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "gstr2b")


def _load_fixture(name: str) -> dict:
    with open(os.path.join(_FIXTURE_DIR, name)) as f:
        return json.load(f)


# ── Helper: minimal books item ────────────────────────────────────────────────

def _books_item(inv_no: str, gstin: str, taxable: float = 10000.0,
                cgst: float = 900.0, sgst: float = 900.0, igst: float = 0.0,
                total: float = 11800.0) -> dict:
    return {
        "supplier_inv": inv_no,
        "gst_no":       gstin,
        "amount":       taxable,
        "cgst":         cgst,
        "sgst":         sgst,
        "igst":         igst,
        "total_amount": total,
    }


# ── GSTIN / Invoice normalization ─────────────────────────────────────────────

class TestNormalization(unittest.TestCase):

    def test_gstin_strip_spaces(self):
        self.assertEqual(normalize_gstin("27AAAAA1111A1Z1"), "27AAAAA1111A1Z1")
        self.assertEqual(normalize_gstin("  27AAAAA1111A1Z1  "), "27AAAAA1111A1Z1")

    def test_gstin_lowercase_to_upper(self):
        self.assertEqual(normalize_gstin("27aaaaa1111a1z1"), "27AAAAA1111A1Z1")

    def test_gstin_strips_punctuation(self):
        self.assertEqual(normalize_gstin("27-AAAAA-1111-A1Z1"), "27AAAAA1111A1Z1")

    def test_inv_normalize_slashes(self):
        self.assertEqual(normalize_inv("INV/2024/001"), "INV2024001")

    def test_inv_normalize_hyphens(self):
        self.assertEqual(normalize_inv("INV-2024-001"), "INV2024001")

    def test_inv_normalize_spaces(self):
        self.assertEqual(normalize_inv("INV 2024 001"), "INV2024001")

    def test_inv_case_insensitive(self):
        self.assertEqual(normalize_inv("inv/2024/001"), "INV2024001")

    def test_inv_empty_returns_empty(self):
        self.assertEqual(normalize_inv(""), "")
        self.assertEqual(normalize_inv(None), "")

    def test_gstin_empty_returns_empty(self):
        self.assertEqual(normalize_gstin(""), "")
        self.assertEqual(normalize_gstin(None), "")


# ── parse_gstr2b ──────────────────────────────────────────────────────────────

class TestParseGSTR2B(unittest.TestCase):

    def test_shape_a_fixture_parsed(self):
        raw = _load_fixture("sample_gstr2b.json")
        records = parse_gstr2b(raw)
        self.assertEqual(len(records), 2)

    def test_shape_a_gstin_normalised(self):
        raw = _load_fixture("sample_gstr2b.json")
        records = parse_gstr2b(raw)
        gstins = {r["gstin"] for r in records}
        self.assertIn("27DDDDD4444D4Z4", gstins)

    def test_shape_a_amounts_aggregated(self):
        raw = _load_fixture("sample_gstr2b.json")
        records = parse_gstr2b(raw)
        rec = next(r for r in records if "DDDDD" in r["gstin"])
        self.assertAlmostEqual(rec["taxable_val"], 860000.0, places=2)
        self.assertAlmostEqual(rec["cgst"], 77400.0, places=2)
        self.assertAlmostEqual(rec["sgst"], 77400.0, places=2)

    def test_shape_a_norm_key_set(self):
        raw = _load_fixture("sample_gstr2b.json")
        for rec in parse_gstr2b(raw):
            self.assertIn("_norm_key", rec)
            self.assertIn("||", rec["_norm_key"])

    def test_shape_b_simplified(self):
        """Shape B: b2b array directly at root level (no data.docdata wrapper)."""
        raw = {
            "b2b": [
                {
                    "ctin": "29EEEEE5555E5Z5",
                    "inv": [
                        {
                            "inum": "SI/001",
                            "dt": "01-04-2024",
                            "val": 11800.0,
                            "itms": [{"itm_det": {"txval": 10000.0, "cgst": 900.0, "sgst": 900.0, "igst": 0.0}}],
                        }
                    ],
                }
            ]
        }
        records = parse_gstr2b(raw)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["gstin"], "29EEEEE5555E5Z5")

    def test_empty_gstr2b_returns_empty_list(self):
        self.assertEqual(parse_gstr2b({}), [])

    def test_record_without_inv_no_skipped(self):
        raw = {
            "b2b": [
                {"ctin": "27AAAAA1111A1Z1", "inv": [{"dt": "01-04-2024", "val": 100.0}]}
            ]
        }
        records = parse_gstr2b(raw)
        self.assertEqual(len(records), 0)


# ── reconcile() statuses ──────────────────────────────────────────────────────

class TestReconcileStatuses(unittest.TestCase):

    def setUp(self):
        raw = _load_fixture("sample_gstr2b.json")
        self.gstr2b = parse_gstr2b(raw)

    def test_perfect_match(self):
        books = [_books_item(
            inv_no="PURCH/2024/007",
            gstin="27DDDDD4444D4Z4",
            taxable=860000.0,
            cgst=77400.0,
            sgst=77400.0,
            igst=0.0,
            total=1014800.0,
        )]
        result = reconcile(books, self.gstr2b)
        row = result["rows"][0]
        self.assertEqual(row["recon_status"], "matched")
        self.assertAlmostEqual(row["diff_amount"], 0.0, places=2)

    def test_missing_in_2b(self):
        books = [_books_item(
            inv_no="UNKNOWN/INVOICE/999",
            gstin="27FFFFF6666F6Z6",
        )]
        result = reconcile(books, self.gstr2b)
        row = result["rows"][0]
        self.assertEqual(row["recon_status"], "missing_in_2b")

    def test_mismatch_amount_over_tolerance(self):
        books = [_books_item(
            inv_no="PURCH/2024/007",
            gstin="27DDDDD4444D4Z4",
            taxable=860000.0,
            cgst=77400.0,
            sgst=77400.0,
            igst=0.0,
            total=1014850.0,   # ₹50 off — beyond ₹2 tolerance
        )]
        result = reconcile(books, self.gstr2b)
        row = result["rows"][0]
        self.assertEqual(row["recon_status"], "mismatch")

    def test_not_in_books_detected(self):
        """Invoice exists in 2B but not in books → not_in_books."""
        books = []   # empty books
        result = reconcile(books, self.gstr2b)
        self.assertGreater(len(result["extra"]), 0)
        for extra in result["extra"]:
            self.assertEqual(extra.get("recon_status"), "not_in_books")

    def test_summary_counts_correct(self):
        books = [
            _books_item("PURCH/2024/007", "27DDDDD4444D4Z4",
                        taxable=860000.0, cgst=77400.0, sgst=77400.0, total=1014800.0),
            _books_item("NOPE/000", "27GGGG7777G7Z7"),  # missing in 2B
        ]
        result = reconcile(books, self.gstr2b)
        # summary["counts"] contains per-status row counts
        counts = result["summary"]["counts"]
        self.assertEqual(counts["matched"], 1)
        self.assertEqual(counts["missing_in_2b"], 1)


# ── ₹2 tolerance boundary ─────────────────────────────────────────────────────

class TestAmountTolerance(unittest.TestCase):

    def setUp(self):
        # Minimal 2B with a single record at ₹11800
        self.gstr2b_simple = [{
            "gstin": "27AAAAA1111A1Z1",
            "inv_no": "INV001",
            "inv_date": "01-04-2024",
            "taxable_val": 10000.0,
            "igst": 0.0,
            "cgst": 900.0,
            "sgst": 900.0,
            "total_val": 11800.0,
            "_norm_key": "27AAAAA1111A1Z1||INV001",
        }]

    def _recon(self, total: float) -> str:
        books = [_books_item("INV001", "27AAAAA1111A1Z1",
                             taxable=10000.0, cgst=900.0, sgst=900.0, total=total)]
        return reconcile(books, self.gstr2b_simple)["rows"][0]["recon_status"]

    def test_exact_match(self):
        self.assertEqual(self._recon(11800.0), "matched")

    def test_within_tolerance_low(self):
        self.assertEqual(self._recon(11799.0), "matched")   # ₹1 under

    def test_within_tolerance_high(self):
        self.assertEqual(self._recon(11802.0), "matched")   # ₹2 over (boundary)

    def test_just_over_tolerance(self):
        self.assertEqual(self._recon(11802.01), "mismatch")   # ₹2.01 over

    def test_tolerance_constant_is_2(self):
        self.assertEqual(AMOUNT_TOLERANCE, 2.0)


# ── Multi-line item aggregation ───────────────────────────────────────────────

class TestMultiLineAggregation(unittest.TestCase):

    def setUp(self):
        # 2B record with ₹1,18,000 total (two line-item invoice summed)
        self.gstr2b = [{
            "gstin": "27AAAAA1111A1Z1",
            "inv_no": "MULTI/001",
            "inv_date": "01-04-2024",
            "taxable_val": 200000.0,
            "igst": 0.0,
            "cgst": 18000.0,
            "sgst": 18000.0,
            "total_val": 236000.0,
            "_norm_key": "27AAAAA1111A1Z1||MULTI001",
        }]

    def test_two_lines_same_invoice_aggregated(self):
        """Two book rows for the same invoice must aggregate before matching."""
        books = [
            _books_item("MULTI/001", "27AAAAA1111A1Z1",
                        taxable=100000.0, cgst=9000.0, sgst=9000.0, total=118000.0),
            _books_item("MULTI/001", "27AAAAA1111A1Z1",
                        taxable=100000.0, cgst=9000.0, sgst=9000.0, total=118000.0),
        ]
        result = reconcile(books, self.gstr2b)
        # Both rows get the same status from the aggregated match
        self.assertTrue(all(r["recon_status"] == "matched" for r in result["rows"]))

    def test_aggregated_diff_amount_correct(self):
        books = [
            _books_item("MULTI/001", "27AAAAA1111A1Z1",
                        taxable=100000.0, cgst=9000.0, sgst=9000.0, total=118000.0),
            _books_item("MULTI/001", "27AAAAA1111A1Z1",
                        taxable=100000.0, cgst=9000.0, sgst=9000.0, total=118000.0),
        ]
        result = reconcile(books, self.gstr2b)
        self.assertAlmostEqual(result["rows"][0]["diff_amount"], 0.0, places=2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
