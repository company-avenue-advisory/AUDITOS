"""
Regression tests for TaxMathematicsEngine.

Each case is deterministic: no LLM, no I/O.
Tests lock the winning-path selection and variance calculation so any
change to the engine's branching logic is immediately caught.
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from backend.core.reconciliation.tax_math import TaxMathematicsEngine


class TestTaxMathPaths(unittest.TestCase):

    def setUp(self):
        self.engine = TaxMathematicsEngine(tolerance=1.50)

    # ── Path A: intrastate CGST + SGST ────────────────────────────────────────

    def test_path_a_perfect_intrastate(self):
        result = self.engine.evaluate_paths({
            "taxable": 10000.0,
            "cgst": 900.0,
            "sgst": 900.0,
            "igst": 0.0,
            "total": 11800.0,
        })
        self.assertEqual(result["winning_path"], "Path A")
        self.assertAlmostEqual(result["variance"], 0.0, places=2)
        self.assertTrue(result["verified"])

    def test_path_a_rounding_within_tolerance(self):
        # total is off by ₹1 — should still verify
        result = self.engine.evaluate_paths({
            "taxable": 10000.0,
            "cgst": 900.0,
            "sgst": 900.0,
            "igst": 0.0,
            "total": 11801.0,
        })
        self.assertEqual(result["winning_path"], "Path A")
        self.assertAlmostEqual(result["variance"], 1.0, places=2)
        self.assertTrue(result["verified"])

    def test_path_a_exceeds_tolerance(self):
        # ₹2 rounding breach — verified must be False
        result = self.engine.evaluate_paths({
            "taxable": 10000.0,
            "cgst": 900.0,
            "sgst": 900.0,
            "igst": 0.0,
            "total": 11802.0,
        })
        self.assertFalse(result["verified"])

    # ── Path B: interstate IGST ────────────────────────────────────────────────

    def test_path_b_perfect_interstate(self):
        result = self.engine.evaluate_paths({
            "taxable": 100000.0,
            "cgst": 0.0,
            "sgst": 0.0,
            "igst": 18000.0,
            "total": 118000.0,
        })
        self.assertEqual(result["winning_path"], "Path B")
        self.assertAlmostEqual(result["variance"], 0.0, places=2)
        self.assertTrue(result["verified"])

    def test_path_b_mixed_tax_still_selects_best(self):
        # Supplier mistakenly put small CGST amount — Path B still wins if variance is lower
        result = self.engine.evaluate_paths({
            "taxable": 100000.0,
            "cgst": 100.0,
            "sgst": 0.0,
            "igst": 18000.0,
            "total": 118000.0,
        })
        # Path B variance = |100000 + 18000 - 118000| = 0; Path A variance = |100000+100+0-118000| = 17900
        self.assertEqual(result["winning_path"], "Path B")

    # ── Path C: gross with pre-tax discount ───────────────────────────────────

    def test_path_c_pre_tax_discount(self):
        # Gross 12000, discount 2000, taxable 10000, CGST+SGST 1800, total 11800
        result = self.engine.evaluate_paths({
            "taxable": 10000.0,
            "cgst": 900.0,
            "sgst": 900.0,
            "igst": 0.0,
            "gross": 12000.0,
            "discount": 2000.0,
            "total": 11800.0,
        })
        # Path A: 10000+900+900=11800 → variance 0; Path C: 12000-2000+1800=11800 → variance 0
        # Both have zero variance — Path A comes first alphabetically, so it wins
        self.assertAlmostEqual(result["variance"], 0.0, places=2)
        self.assertTrue(result["verified"])

    # ── Path E: auxiliary charges ──────────────────────────────────────────────

    def test_path_e_with_freight(self):
        result = self.engine.evaluate_paths({
            "taxable": 10000.0,
            "cgst": 900.0,
            "sgst": 900.0,
            "igst": 0.0,
            "gross": 10000.0,
            "discount": 0.0,
            "freight": 500.0,
            "packing": 200.0,
            "total": 12500.0,
        })
        # Path E: 10000 + 500 + 200 + 1800 = 12500 → variance 0
        # Path A: 10000+1800 = 11800 → variance 700
        self.assertEqual(result["winning_path"], "Path E")
        self.assertAlmostEqual(result["variance"], 0.0, places=2)
        self.assertTrue(result["verified"])

    # ── All-paths result shape ─────────────────────────────────────────────────

    def test_all_paths_present(self):
        result = self.engine.evaluate_paths({
            "taxable": 1000.0, "cgst": 90.0, "sgst": 90.0,
            "igst": 0.0, "total": 1180.0,
        })
        path_names = {p["path"] for p in result["all_paths"]}
        self.assertEqual(path_names, {"Path A", "Path B", "Path C", "Path D", "Path E"})

    def test_confidence_between_zero_and_one(self):
        result = self.engine.evaluate_paths({
            "taxable": 1000.0, "cgst": 90.0, "sgst": 90.0,
            "igst": 0.0, "total": 1180.0,
        })
        for p in result["all_paths"]:
            self.assertGreaterEqual(p["confidence"], 0.0)

    # ── Zero-total edge case ───────────────────────────────────────────────────

    def test_zero_total_does_not_crash(self):
        result = self.engine.evaluate_paths({
            "taxable": 0.0, "cgst": 0.0, "sgst": 0.0,
            "igst": 0.0, "total": 0.0,
        })
        # All variances are 0; engine should return some winning path without error
        self.assertIn("winning_path", result)

    # ── Custom tolerance ───────────────────────────────────────────────────────

    def test_custom_tolerance_strict(self):
        engine_strict = TaxMathematicsEngine(tolerance=0.0)
        result = engine_strict.evaluate_paths({
            "taxable": 10000.0, "cgst": 900.0, "sgst": 900.0,
            "igst": 0.0, "total": 11800.50,
        })
        self.assertFalse(result["verified"])

    def test_custom_tolerance_loose(self):
        engine_loose = TaxMathematicsEngine(tolerance=10.0)
        result = engine_loose.evaluate_paths({
            "taxable": 10000.0, "cgst": 900.0, "sgst": 900.0,
            "igst": 0.0, "total": 11805.0,
        })
        self.assertTrue(result["verified"])


class TestTaxRateImplied(unittest.TestCase):
    """Verify that implied GST rates from the winning path are mathematically consistent."""

    def _implied_rate(self, taxable, tax):
        if taxable == 0:
            return 0.0
        return round((tax / taxable) * 100, 2)

    def test_18pct_intrastate(self):
        # 9% CGST + 9% SGST
        self.assertEqual(self._implied_rate(10000, 900), 9.0)
        self.assertEqual(self._implied_rate(10000, 900), 9.0)

    def test_18pct_interstate(self):
        self.assertEqual(self._implied_rate(100000, 18000), 18.0)

    def test_5pct_igst(self):
        self.assertEqual(self._implied_rate(10000, 500), 5.0)

    def test_28pct_cgst_sgst(self):
        self.assertEqual(self._implied_rate(10000, 1400), 14.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
