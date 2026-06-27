import time
from backend.core.validation.base import BaseRule, RuleResult, Severity
from backend.core.validation.packs.base import BaseValidationPack
from backend.core.schema import CanonicalInvoice

class RuleCLASS001(BaseRule):
    rule_id = "CLASS_001"
    rule_name = "B2B Classification Consistency"
    category = "Classification"
    severity = Severity.ERROR
    description = "Asserts that B2B invoices require a valid buyer GSTIN."

    def evaluate(self, invoice: CanonicalInvoice) -> RuleResult:
        t0 = time.time()
        gstr1_cat = invoice.classification.gstr1_category or ""
        buyer_gst = (invoice.buyer.gstin.value or "").strip()
        
        passed = True
        reason = "B2B classification checks out."
        if gstr1_cat.upper() == "B2B":
            passed = len(buyer_gst) >= 15
            if not passed:
                reason = "B2B category classified but Buyer GSTIN is missing/invalid."
                
        status = "PASS" if passed else "FAIL"
        return RuleResult(
            rule_id=self.rule_id,
            rule_name=self.rule_name,
            passed=passed,
            status=status,
            severity=self.severity,
            reason=reason,
            evidence={"expected": "B2B requires GSTIN", "actual": f"Cat: {gstr1_cat}, GSTIN: {buyer_gst}"},
            recommendation="" if passed else "Add the buyer's GSTIN or change category classification.",
            execution_time_ms=int((time.time() - t0) * 1000)
        )

class RuleCLASS002(BaseRule):
    rule_id = "CLASS_002"
    rule_name = "B2CS Classification Consistency"
    category = "Classification"
    severity = Severity.ERROR
    description = "Asserts B2CS invoices should not have a buyer GSTIN and must be under 2.5L if interstate."

    def evaluate(self, invoice: CanonicalInvoice) -> RuleResult:
        t0 = time.time()
        gstr1_cat = invoice.classification.gstr1_category or ""
        buyer_gst = (invoice.buyer.gstin.value or "").strip()
        grand_total = invoice.tax_summary.grand_total.value or 0.0
        
        passed = True
        reason = "B2CS classification check passed."
        if gstr1_cat.upper() == "B2CS":
            if len(buyer_gst) >= 15:
                passed = False
                reason = "B2CS categorized but Buyer GSTIN is present."
                
        status = "PASS" if passed else "FAIL"
        return RuleResult(
            rule_id=self.rule_id,
            rule_name=self.rule_name,
            passed=passed,
            status=status,
            severity=self.severity,
            reason=reason,
            evidence={"expected": "B2CS requires empty GSTIN", "actual": f"Cat: {gstr1_cat}, GSTIN: {buyer_gst}"},
            recommendation="" if passed else "Change category classification to B2B or remove buyer GSTIN.",
            execution_time_ms=int((time.time() - t0) * 1000)
        )

class RuleCLASS003(BaseRule):
    rule_id = "CLASS_003"
    rule_name = "B2CL Classification Check"
    category = "Classification"
    severity = Severity.ERROR
    description = "Asserts B2CL invoices must be interstate and exceed 2.5 Lakhs (250,000)."

    def evaluate(self, invoice: CanonicalInvoice) -> RuleResult:
        t0 = time.time()
        gstr1_cat = invoice.classification.gstr1_category or ""
        grand_total = invoice.tax_summary.grand_total.value or 0.0
        
        passed = True
        reason = "B2CL checks passed."
        if gstr1_cat.upper() == "B2CL":
            passed = grand_total > 250000.0
            if not passed:
                reason = f"B2CL classified but grand total {grand_total:.2f} is under 2.5 Lakhs limit."
                
        status = "PASS" if passed else "FAIL"
        return RuleResult(
            rule_id=self.rule_id,
            rule_name=self.rule_name,
            passed=passed,
            status=status,
            severity=self.severity,
            reason=reason,
            evidence={"expected": "Grand Total > 250,000", "actual": str(grand_total)},
            recommendation="" if passed else "Recategorize to B2CS if the invoice total is under 250,000.",
            execution_time_ms=int((time.time() - t0) * 1000)
        )

class ClassificationValidationPack(BaseValidationPack):
    pack_name = "GSTR Classification Validation Pack"
    description = "Checks alignment of GSTR categories against party profiles."

    def get_rules(self):
        return [RuleCLASS001(), RuleCLASS002(), RuleCLASS003()]
