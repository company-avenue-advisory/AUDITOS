import time
from backend.core.validation.base import BaseRule, RuleResult, Severity
from backend.core.validation.packs.base import BaseValidationPack
from backend.core.schema import CanonicalInvoice

class RuleMATH001(BaseRule):
    rule_id = "MATH_001"
    rule_name = "Grand Total Balance Check"
    category = "Math"
    severity = Severity.BLOCKER
    description = "Asserts that Taxable Value + CGST + SGST + IGST + CESS + Roundoff equals Grand Total."

    def evaluate(self, invoice: CanonicalInvoice) -> RuleResult:
        t0 = time.time()
        taxable = invoice.tax_summary.taxable_value.value or 0.0
        cgst = invoice.tax_summary.cgst_amount.value or 0.0
        sgst = invoice.tax_summary.sgst_amount.value or 0.0
        igst = invoice.tax_summary.igst_amount.value or 0.0
        cess = invoice.tax_summary.cess_amount.value or 0.0
        round_off = invoice.tax_summary.round_off.value or 0.0
        grand_total = invoice.tax_summary.grand_total.value or 0.0
        
        calculated_total = taxable + cgst + sgst + igst + cess + round_off
        passed = abs(calculated_total - grand_total) <= 1.5
        status = "PASS" if passed else "FAIL"
        
        return RuleResult(
            rule_id=self.rule_id,
            rule_name=self.rule_name,
            passed=passed,
            status=status,
            severity=self.severity,
            reason="Grand total equals sum of taxable values and tax details." if passed else "Variance detected between calculated and overall invoice totals.",
            evidence={
                "expected": f"Calculated: {calculated_total:.2f}", 
                "actual": f"Grand Total: {grand_total:.2f}"
            },
            recommendation="" if passed else f"Reconcile math totals. Variance is {calculated_total - grand_total:.2f}.",
            execution_time_ms=int((time.time() - t0) * 1000)
        )

class RuleMATH002(BaseRule):
    rule_id = "MATH_002"
    rule_name = "Positive Total Check"
    category = "Math"
    severity = Severity.BLOCKER
    description = "Asserts that grand total is a positive value."

    def evaluate(self, invoice: CanonicalInvoice) -> RuleResult:
        t0 = time.time()
        grand_total = invoice.tax_summary.grand_total.value or 0.0
        passed = grand_total > 0.0
        status = "PASS" if passed else "FAIL"
        
        return RuleResult(
            rule_id=self.rule_id,
            rule_name=self.rule_name,
            passed=passed,
            status=status,
            severity=self.severity,
            reason="Grand total is positive." if passed else "Total invoice value is zero or negative.",
            evidence={"expected": "> 0.0", "actual": str(grand_total)},
            recommendation="" if passed else "Verify the invoice items and amounts are positive values.",
            execution_time_ms=int((time.time() - t0) * 1000)
        )

class RuleGST008(BaseRule):
    rule_id = "GST_008"
    rule_name = "Standard GST Slabs Validation"
    category = "Tax"
    severity = Severity.ERROR
    description = "Ensures line item rates fall within approved standard GST slabs (0%, 5%, 12%, 18%, 28%)."

    def evaluate(self, invoice: CanonicalInvoice) -> RuleResult:
        t0 = time.time()
        passed = True
        invalid_rates = []
        valid_slabs = {0.0, 5.0, 12.0, 18.0, 28.0}
        
        for item in invoice.line_items:
            taxable = item.taxable_value.value or 0.0
            cgst = item.cgst_amount.value or 0.0
            sgst = item.sgst_amount.value or 0.0
            igst = item.igst_amount.value or 0.0
            total_tax = cgst + sgst + igst
            
            if taxable > 0:
                calc_rate = round((total_tax / taxable) * 100, 1)
                is_valid = any(abs(calc_rate - slab) <= 0.5 for slab in valid_slabs)
                if not is_valid:
                    passed = False
                    invalid_rates.append(calc_rate)
                    
        status = "PASS" if passed else "FAIL"
        return RuleResult(
            rule_id=self.rule_id,
            rule_name=self.rule_name,
            passed=passed,
            status=status,
            severity=self.severity,
            reason="All items match standard GST rate slabs." if passed else f"GST rates {invalid_rates} do not fall in standard slabs.",
            evidence={"expected": "0%, 5%, 12%, 18%, 28%", "actual": str(invalid_rates) if not passed else "0%, 5%, 12%, 18%, 28%"},
            recommendation="" if passed else "Select a standard GST slab for the flagged line items.",
            execution_time_ms=int((time.time() - t0) * 1000)
        )

class AccountingValidationPack(BaseValidationPack):
    pack_name = "Accounting & Mathematical Validation Pack"
    description = "Checks verification of grand totals and GST tax rate slabs."

    def get_rules(self):
        return [RuleMATH001(), RuleMATH002(), RuleGST008()]
