import time
import re
from backend.core.validation.base import BaseRule, RuleResult, Severity
from backend.core.validation.packs.base import BaseValidationPack
from backend.core.schema import CanonicalInvoice

GSTIN_REGEX = re.compile(r'^\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}Z[A-Z\d]{1}$')

INDIAN_STATES = {
    "01": "JAMMU AND KASHMIR", "02": "HIMACHAL PRADESH", "03": "PUNJAB", "04": "CHANDIGARH", 
    "05": "UTTARAKHAND", "06": "HARYANA", "07": "DELHI", "08": "RAJASTHAN", "09": "UTTAR PRADESH", 
    "10": "BIHAR", "11": "SIKKIM", "12": "ARUNACHAL PRADESH", "13": "NAGALAND", "14": "MANIPUR", 
    "15": "MIZORAM", "16": "TRIPURA", "17": "MEGHALAYA", "18": "ASSAM", "19": "WEST BENGAL", 
    "20": "JHARKHAND", "21": "ODISHA", "22": "CHHATTISGARH", "23": "MADHYA PRADESH", 
    "24": "GUJARAT", "26": "DADRA AND NAGAR HAVELI AND DAMAN AND DIU", "27": "MAHARASHTRA", 
    "29": "KARNATAKA", "30": "GOA", "31": "LAKSHADWEEP", "32": "KERALA", "33": "TAMIL NADU", 
    "34": "PUDUCHERRY", "35": "ANDAMAN AND NICOBAR ISLANDS", "36": "TELANGANA", "37": "ANDHRA PRADESH", 
    "38": "LADAKH"
}

class RuleGST001(BaseRule):
    rule_id = "GST_001"
    rule_name = "Supplier GSTIN Format"
    category = "GST"
    severity = Severity.BLOCKER
    description = "Checks that Supplier GSTIN complies with the standard 15-character format."

    def evaluate(self, invoice: CanonicalInvoice) -> RuleResult:
        t0 = time.time()
        val = (invoice.supplier.gstin.value or "").strip().upper()
        passed = bool(GSTIN_REGEX.match(val))
        status = "PASS" if passed else "FAIL"
        
        return RuleResult(
            rule_id=self.rule_id,
            rule_name=self.rule_name,
            passed=passed,
            status=status,
            severity=self.severity,
            reason="Supplier GSTIN is registered with a correct format prefix." if passed else "Invalid Supplier GSTIN sequence format.",
            evidence={"expected": "15-char alphanumeric", "actual": val or "None"},
            recommendation="" if passed else "Verify and input a correct Supplier GSTIN.",
            execution_time_ms=int((time.time() - t0) * 1000)
        )

class RuleGST002(BaseRule):
    rule_id = "GST_002"
    rule_name = "GSTIN Format Verification"
    category = "GST"
    severity = Severity.ERROR
    description = "Dependency check verifying buyer GSTIN structure."
    depends_on = ["GST_001"] # Just as an example dependency

    def evaluate(self, invoice: CanonicalInvoice) -> RuleResult:
        t0 = time.time()
        val = (invoice.buyer.gstin.value or "").strip().upper()
        passed = bool(GSTIN_REGEX.match(val))
        status = "PASS" if passed else "FAIL"
        
        return RuleResult(
            rule_id=self.rule_id,
            rule_name=self.rule_name,
            passed=passed,
            status=status,
            severity=self.severity,
            reason="Buyer GSTIN format is correct." if passed else "Buyer GSTIN format is invalid.",
            evidence={"expected": "15-char alphanumeric", "actual": val or "None"},
            recommendation="" if passed else "Verify and input a correct Buyer GSTIN.",
            execution_time_ms=int((time.time() - t0) * 1000)
        )

class RuleGST003(BaseRule):
    rule_id = "GST_003"
    rule_name = "Supplier GST State Code Match"
    category = "GST"
    severity = Severity.ERROR
    description = "Ensures Supplier state code matches start digits of Supplier GSTIN."

    def evaluate(self, invoice: CanonicalInvoice) -> RuleResult:
        t0 = time.time()
        gstin = (invoice.supplier.gstin.value or "").strip()
        state_code = (invoice.supplier.state_code.value or "").strip()
        
        passed = True
        if len(gstin) >= 2 and state_code:
            passed = gstin[:2] == state_code
            
        status = "PASS" if passed else "FAIL"
        return RuleResult(
            rule_id=self.rule_id,
            rule_name=self.rule_name,
            passed=passed,
            status=status,
            severity=self.severity,
            reason="State code prefix aligns with Supplier GSTIN." if passed else "State code prefix mismatches Supplier GSTIN.",
            evidence={"expected": f"Prefix matches: {state_code}", "actual": f"GSTIN: {gstin}"},
            recommendation="" if passed else "Correct the State Code or Supplier GSTIN prefix.",
            execution_time_ms=int((time.time() - t0) * 1000)
        )

class RuleGST004(BaseRule):
    rule_id = "GST_004"
    rule_name = "Place of Supply Code Match"
    category = "GST"
    severity = Severity.ERROR
    description = "Checks that Place of Supply aligns with Buyer/Supplier GSTIN depending on transaction type."

    def evaluate(self, invoice: CanonicalInvoice) -> RuleResult:
        t0 = time.time()
        pos = (invoice.invoice_metadata.place_of_supply.value or "").strip().upper()
        
        pos_clean = re.sub(r'[^A-Z0-9 ]', '', pos)
        passed = False
        for code, name in INDIAN_STATES.items():
            if pos_clean == code or pos_clean in name or name in pos_clean:
                passed = True
                break
                
        status = "PASS" if passed else "FAIL"
        return RuleResult(
            rule_id=self.rule_id,
            rule_name=self.rule_name,
            passed=passed,
            status=status,
            severity=self.severity,
            reason=f"Place of Supply {pos} matches a valid state." if passed else "Place of Supply does not match any Indian State.",
            evidence={"expected": "Valid state name or state code", "actual": pos or "None"},
            recommendation="" if passed else "Enter a correct POS value matching registered State list.",
            execution_time_ms=int((time.time() - t0) * 1000)
        )

class GSTValidationPack(BaseValidationPack):
    pack_name = "GST Compliance Validation Pack"
    description = "Pack verifying GST registrations and State prefix alignments."

    def get_rules(self):
        return [RuleGST001(), RuleGST002(), RuleGST003(), RuleGST004()]
