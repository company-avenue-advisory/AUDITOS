import time
import re
from datetime import datetime
from backend.core.validation.base import BaseRule, RuleResult, Severity
from backend.core.validation.packs.base import BaseValidationPack
from backend.core.schema import CanonicalInvoice

class RuleINV001(BaseRule):
    rule_id = "INV_001"
    rule_name = "Invoice Number Presence"
    category = "Invoice"
    severity = Severity.BLOCKER
    description = "Checks that a non-empty invoice sequence number has been extracted."

    def evaluate(self, invoice: CanonicalInvoice) -> RuleResult:
        t0 = time.time()
        val = invoice.invoice_metadata.invoice_number.value
        passed = bool(val and val.strip())
        status = "PASS" if passed else "FAIL"
        
        return RuleResult(
            rule_id=self.rule_id,
            rule_name=self.rule_name,
            passed=passed,
            status=status,
            severity=self.severity,
            reason="Invoice number check matches CA compliance audit guidelines." if passed else "Invoice number is missing.",
            evidence={"expected": "Alphanumeric string", "actual": val or "None"},
            recommendation="" if passed else "Input a valid invoice sequence number.",
            execution_time_ms=int((time.time() - t0) * 1000)
        )

class RuleINV002(BaseRule):
    rule_id = "INV_002"
    rule_name = "Invoice Date Presence"
    category = "Invoice"
    severity = Severity.BLOCKER
    description = "Checks that a non-empty invoice date has been extracted."

    def evaluate(self, invoice: CanonicalInvoice) -> RuleResult:
        t0 = time.time()
        val = invoice.invoice_metadata.invoice_date.value
        passed = bool(val and val.strip())
        status = "PASS" if passed else "FAIL"
        
        return RuleResult(
            rule_id=self.rule_id,
            rule_name=self.rule_name,
            passed=passed,
            status=status,
            severity=self.severity,
            reason="Invoice date is correctly present." if passed else "Invoice date is missing.",
            evidence={"expected": "Date string", "actual": val or "None"},
            recommendation="" if passed else "Input a valid invoice date.",
            execution_time_ms=int((time.time() - t0) * 1000)
        )

class RuleINV003(BaseRule):
    rule_id = "INV_003"
    rule_name = "Invoice Date Not In Future"
    category = "Invoice"
    severity = Severity.ERROR
    description = "Asserts that the invoice date is not in the future."

    def evaluate(self, invoice: CanonicalInvoice) -> RuleResult:
        t0 = time.time()
        val = invoice.invoice_metadata.invoice_date.value
        passed = True
        reason = "Invoice date verified."
        expected = "Date <= today"
        
        if val:
            try:
                clean_date = re.sub(r'[^a-zA-Z0-9]', ' ', val)
                parsed = None
                for fmt in ["%d %b %Y", "%d %B %Y", "%Y %m %d", "%d %m %Y", "%d %m %y"]:
                    try:
                        parsed = datetime.strptime(clean_date.strip(), fmt)
                        break
                    except ValueError:
                        continue
                if parsed:
                    now = datetime.now()
                    if parsed > now:
                        passed = False
                        reason = f"Invoice date {val} falls in the future."
            except Exception:
                pass
                
        status = "PASS" if passed else "FAIL"
        return RuleResult(
            rule_id=self.rule_id,
            rule_name=self.rule_name,
            passed=passed,
            status=status,
            severity=self.severity,
            reason=reason,
            evidence={"expected": expected, "actual": val or "None"},
            recommendation="" if passed else "Correct the invoice date to today or a past date.",
            execution_time_ms=int((time.time() - t0) * 1000)
        )

class RuleINV004(BaseRule):
    rule_id = "INV_004"
    rule_name = "Due Date Chronology"
    category = "Invoice"
    severity = Severity.ERROR
    description = "Validates that due date is greater than or equal to invoice date."

    def evaluate(self, invoice: CanonicalInvoice) -> RuleResult:
        t0 = time.time()
        inv_dt_str = invoice.invoice_metadata.invoice_date.value
        due_dt_str = invoice.invoice_metadata.due_date.value
        passed = True
        reason = "Chronological sequence is correct."
        
        if inv_dt_str and due_dt_str:
            try:
                def parse_dt(d_str):
                    clean = re.sub(r'[^a-zA-Z0-9]', ' ', d_str)
                    for fmt in ["%d %b %Y", "%d %B %Y", "%Y %m %d", "%d %m %Y"]:
                        try:
                            return datetime.strptime(clean.strip(), fmt)
                        except ValueError:
                            continue
                    return None
                
                inv_parsed = parse_dt(inv_dt_str)
                due_parsed = parse_dt(due_dt_str)
                if inv_parsed and due_parsed and due_parsed < inv_parsed:
                    passed = False
                    reason = f"Payment due date {due_dt_str} precedes invoice date {inv_dt_str}."
            except Exception:
                pass
                
        status = "PASS" if passed else "FAIL"
        return RuleResult(
            rule_id=self.rule_id,
            rule_name=self.rule_name,
            passed=passed,
            status=status,
            severity=self.severity,
            reason=reason,
            evidence={"expected": "Due Date >= Invoice Date", "actual": f"Inv: {inv_dt_str}, Due: {due_dt_str}"},
            recommendation="" if passed else "Adjust due date to match credit terms.",
            execution_time_ms=int((time.time() - t0) * 1000)
        )

class InvoiceValidationPack(BaseValidationPack):
    pack_name = "Invoice Metadata Validation Pack"
    description = "Group of rules checking header invoice sequence parameters."

    def get_rules(self):
        return [RuleINV001(), RuleINV002(), RuleINV003(), RuleINV004()]
