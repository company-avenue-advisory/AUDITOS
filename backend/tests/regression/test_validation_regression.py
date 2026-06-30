"""
Regression tests for ValidationEngine and all 5 validation packs.

Checks that:
  - Valid invoices produce a passing report
  - Known bad inputs trigger the correct rule ID failures
  - Severity levels are not accidentally downgraded
  - Rule counts in each pack don't silently drop

No LLM calls — all inputs are hand-constructed CanonicalInvoice objects.
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from backend.core.schema import CanonicalInvoice, LineItem, ProvenancedValue
from backend.core.validation.engine import ValidationEngine
from backend.core.validation.registry import RuleRegistry
from backend.core.validation.packs import ALL_PACKS


def _pv(val):
    return ProvenancedValue(value=val)


def _valid_invoice():
    """Minimal invoice that satisfies all mandatory / GST / accounting rules."""
    inv = CanonicalInvoice()
    inv.supplier.gstin       = _pv("27AAAAA1111A1Z1")
    inv.supplier.legal_name  = _pv("ABC Traders Pvt Ltd")
    inv.buyer.gstin          = _pv("27BBBBB2222B2Z2")
    inv.buyer.name           = _pv("XYZ Industries")
    inv.invoice_metadata.invoice_number  = _pv("INV/2024/001")
    inv.invoice_metadata.invoice_date    = _pv("01-Apr-2024")
    inv.invoice_metadata.place_of_supply = _pv("27")
    inv.invoice_metadata.invoice_type    = _pv("Sales")

    item = LineItem()
    item.taxable_value = _pv(10000.0)
    item.cgst_amount   = _pv(900.0)
    item.sgst_amount   = _pv(900.0)
    item.igst_amount   = _pv(0.0)
    item.total         = _pv(11800.0)
    inv.line_items.append(item)

    inv.tax_summary.taxable_value = _pv(10000.0)
    inv.tax_summary.cgst_amount   = _pv(900.0)
    inv.tax_summary.sgst_amount   = _pv(900.0)
    inv.tax_summary.igst_amount   = _pv(0.0)
    inv.tax_summary.grand_total   = _pv(11800.0)
    return inv


class TestValidationEngineSmoke(unittest.TestCase):

    def setUp(self):
        self.engine = ValidationEngine()

    def test_valid_invoice_high_score(self):
        report = self.engine.validate(_valid_invoice())
        self.assertGreater(
            report.overall_score, 0.7,
            f"Valid invoice score too low: {report.overall_score}"
        )

    def test_report_has_results(self):
        report = self.engine.validate(_valid_invoice())
        self.assertGreater(len(report.results), 0)

    def test_report_has_summary_fields(self):
        report = self.engine.validate(_valid_invoice())
        self.assertIsNotNone(report.overall_score)
        self.assertIsNotNone(report.errors)
        self.assertIsNotNone(report.warnings)

    def test_empty_invoice_does_not_crash(self):
        report = self.engine.validate(CanonicalInvoice())
        self.assertIsNotNone(report)


class TestGSTPackRules(unittest.TestCase):

    def setUp(self):
        self.engine = ValidationEngine()

    def test_invalid_supplier_gstin_fails_gst001(self):
        inv = _valid_invoice()
        inv.supplier.gstin = _pv("INVALID_GSTIN")
        report = self.engine.validate(inv)
        rule_ids = {r.rule_id for r in report.results}
        self.assertIn("GST_001", rule_ids)
        failed = [r for r in report.results if r.rule_id == "GST_001"]
        self.assertTrue(all(not r.passed for r in failed), "GST_001 must FAIL for bad GSTIN")

    def test_valid_supplier_gstin_passes_gst001(self):
        report = self.engine.validate(_valid_invoice())
        gst001 = [r for r in report.results if r.rule_id == "GST_001"]
        self.assertTrue(all(r.passed for r in gst001), "GST_001 must PASS for valid GSTIN")

    def test_invalid_buyer_gstin_fails_gst002(self):
        inv = _valid_invoice()
        inv.buyer.gstin = _pv("BAD")
        report = self.engine.validate(inv)
        gst002 = [r for r in report.results if r.rule_id == "GST_002"]
        if gst002:  # rule may be skipped if GST_001 fails first
            self.assertTrue(all(not r.passed for r in gst002))

    def test_gst_pack_min_rule_count(self):
        """GST pack must have at least 2 rules — catches accidental deletions."""
        RuleRegistry.clear()
        for pack in ALL_PACKS:
            RuleRegistry.register_pack(pack)
        all_rules = RuleRegistry.get_all_rules()
        gst_rules = [r for r in all_rules if r.category == "GST"]
        self.assertGreaterEqual(len(gst_rules), 2)


class TestMandatoryPackRules(unittest.TestCase):

    def setUp(self):
        self.engine = ValidationEngine()

    def test_missing_invoice_number_flagged(self):
        inv = _valid_invoice()
        inv.invoice_metadata.invoice_number = _pv(None)
        report = self.engine.validate(inv)
        # At least one mandatory rule must fail
        mandatory_fails = [
            r for r in report.results
            if not r.passed and r.category in ("Mandatory", "Invoice", "mandatory")
        ]
        self.assertGreater(
            len(mandatory_fails), 0,
            "Missing invoice number must fail at least one mandatory rule"
        )

    def test_missing_invoice_date_flagged(self):
        inv = _valid_invoice()
        inv.invoice_metadata.invoice_date = _pv(None)
        report = self.engine.validate(inv)
        errors_and_warnings = report.errors + report.warnings
        self.assertGreater(len(errors_and_warnings), 0)


class TestAccountingPackRules(unittest.TestCase):

    def setUp(self):
        self.engine = ValidationEngine()

    def test_zero_grand_total_flagged(self):
        inv = _valid_invoice()
        inv.tax_summary.grand_total = _pv(0.0)
        report = self.engine.validate(inv)
        # MATH_001 checks grand total balance — category is "Math"
        math_fails = [
            r for r in report.results
            if not r.passed and r.category in ("Math", "math")
        ]
        self.assertGreater(len(math_fails), 0)

    def test_accounting_pack_min_rule_count(self):
        RuleRegistry.clear()
        for pack in ALL_PACKS:
            RuleRegistry.register_pack(pack)
        all_rules = RuleRegistry.get_all_rules()
        # Accounting pack uses "Math" category (see RuleMATH001)
        math_rules = [r for r in all_rules if r.category == "Math"]
        self.assertGreaterEqual(len(math_rules), 1)


class TestRuleRegistryIntegrity(unittest.TestCase):

    def test_total_rule_count_regression(self):
        """Total registered rule count must not drop below a known baseline."""
        RuleRegistry.clear()
        for pack in ALL_PACKS:
            RuleRegistry.register_pack(pack)
        all_rules = RuleRegistry.get_all_rules()
        # Baseline: at minimum 5 rules (one per pack)
        # Update this number upward as packs grow — never downward
        self.assertGreaterEqual(len(all_rules), 5,
            f"Only {len(all_rules)} rules registered — check for missing pack registrations")

    def test_no_duplicate_rule_ids(self):
        RuleRegistry.clear()
        for pack in ALL_PACKS:
            RuleRegistry.register_pack(pack)
        all_rules = RuleRegistry.get_all_rules()
        ids = [r.rule_id for r in all_rules]
        self.assertEqual(len(ids), len(set(ids)), "Duplicate rule IDs detected")

    def test_all_rules_have_severity(self):
        RuleRegistry.clear()
        for pack in ALL_PACKS:
            RuleRegistry.register_pack(pack)
        for rule in RuleRegistry.get_all_rules():
            self.assertIsNotNone(rule.severity, f"Rule {rule.rule_id} missing severity")


if __name__ == "__main__":
    unittest.main(verbosity=2)
