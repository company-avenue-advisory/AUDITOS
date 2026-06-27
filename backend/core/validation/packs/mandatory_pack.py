import time
from backend.core.validation.base import BaseRule, RuleResult, Severity
from backend.core.validation.packs.base import BaseValidationPack
from backend.core.schema import CanonicalInvoice

class RuleMAND001(BaseRule):
    rule_id = "MAND_001"
    rule_name = "Party Names Validation"
    category = "Mandatory"
    severity = Severity.BLOCKER
    description = "Checks that both supplier and buyer names are extracted and non-empty."

    def evaluate(self, invoice: CanonicalInvoice) -> RuleResult:
        t0 = time.time()
        supplier = (invoice.supplier.legal_name.value or "").strip()
        buyer = (invoice.buyer.name.value or "").strip()
        
        passed = bool(supplier and buyer)
        status = "PASS" if passed else "FAIL"
        
        return RuleResult(
            rule_id=self.rule_id,
            rule_name=self.rule_name,
            passed=passed,
            status=status,
            severity=self.severity,
            reason="Party names successfully validated." if passed else "Supplier or Buyer name is missing.",
            evidence={"expected": "Both names populated", "actual": f"Supplier: {supplier or 'None'}, Buyer: {buyer or 'None'}"},
            recommendation="" if passed else "Verify and input missing party name headers.",
            execution_time_ms=int((time.time() - t0) * 1000)
        )

class RuleMAND002(BaseRule):
    rule_id = "MAND_002"
    rule_name = "Taxable Value Presence"
    category = "Mandatory"
    severity = Severity.BLOCKER
    description = "Asserts that the invoice taxable value is non-zero."

    def evaluate(self, invoice: CanonicalInvoice) -> RuleResult:
        t0 = time.time()
        taxable = invoice.tax_summary.taxable_value.value or 0.0
        passed = taxable != 0.0
        status = "PASS" if passed else "FAIL"
        
        return RuleResult(
            rule_id=self.rule_id,
            rule_name=self.rule_name,
            passed=passed,
            status=status,
            severity=self.severity,
            reason="Taxable value is valid and non-zero." if passed else "Invoice has no taxable base value.",
            evidence={"expected": "Taxable Value != 0.0", "actual": str(taxable)},
            recommendation="" if passed else "Ensure line items taxable values are present.",
            execution_time_ms=int((time.time() - t0) * 1000)
        )

class MandatoryValidationPack(BaseValidationPack):
    pack_name = "Mandatory Fields Validation Pack"
    description = "Validates presence of core transaction descriptors and non-zero base totals."

    def get_rules(self):
        return [RuleMAND001(), RuleMAND002()]
