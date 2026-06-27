import time
from typing import List, Dict, Any
from backend.core.schema import CanonicalInvoice
from backend.core.schema.validation import ValidationReport, ValidationResult
from backend.core.validation.base import RuleResult, Severity
from backend.core.validation.registry import RuleRegistry
from backend.core.validation.packs import ALL_PACKS

class ValidationEngine:
    """
    Refined Chartered Accountant Validation Engine orchestrating Packs,
    Rule Registry, Dependencies, and detailed compliance scoring.
    """
    def __init__(self):
        # Register standard packs at startup
        RuleRegistry.clear()
        for pack in ALL_PACKS:
            RuleRegistry.register_pack(pack)

    def validate(self, invoice: CanonicalInvoice) -> ValidationReport:
        t_start = time.time()
        
        rules = RuleRegistry.get_all_rules()
        
        # Track rule outcomes by ID
        evaluated_results: Dict[str, RuleResult] = {}
        passed_rule_ids = set()
        failed_rule_ids = set()
        
        errors: List[str] = []
        warnings: List[str] = []
        
        math_failed = False
        gst_failed = False
        math_warn = False
        
        # Simple execution queue (resolves simple dependencies since they are pre-sorted or executed sequentially)
        # To support multiple levels, we loop until all rules are evaluated or skipped
        to_evaluate = list(rules)
        
        while to_evaluate:
            rule = to_evaluate.pop(0)
            
            # Check dependencies
            deps_met = True
            failed_deps = []
            for dep_id in rule.depends_on:
                if dep_id not in evaluated_results:
                    # Dependency not run yet, push back to end of queue
                    to_evaluate.append(rule)
                    deps_met = False
                    break
                elif not evaluated_results[dep_id].passed:
                    deps_met = False
                    failed_deps.append(dep_id)
            
            if not deps_met:
                if failed_deps:
                    # Dependencies ran and failed, so this rule is automatically failed
                    res = RuleResult(
                        rule_id=rule.rule_id,
                        rule_name=rule.rule_name,
                        passed=False,
                        status="FAIL",
                        severity=rule.severity,
                        reason=f"Skipped: Dependency rule(s) {failed_deps} failed.",
                        evidence={"expected": "Dependencies pass", "actual": f"Failed dependencies: {failed_deps}"},
                        recommendation=f"Resolve failures in {failed_deps} first.",
                        execution_time_ms=0.0
                    )
                    evaluated_results[rule.rule_id] = res
                    failed_rule_ids.add(rule.rule_id)
                    
                    if rule.severity in [Severity.BLOCKER, Severity.ERROR]:
                        errors.append(f"[{rule.rule_id}] {res.reason}")
                    else:
                        warnings.append(f"[{rule.rule_id}] {res.reason}")
                continue
                
            # Run evaluation
            try:
                t0 = time.time()
                res = rule.evaluate(invoice)
                res.execution_time_ms = int((time.time() - t0) * 1000)
                
                evaluated_results[rule.rule_id] = res
                if res.passed:
                    passed_rule_ids.add(rule.rule_id)
                else:
                    failed_rule_ids.add(rule.rule_id)
                    if res.severity in [Severity.BLOCKER, Severity.ERROR]:
                        errors.append(f"[{rule.rule_id}] {res.reason}")
                    else:
                        warnings.append(f"[{rule.rule_id}] {res.reason}")
                        
                    # Track Math/GST sub-status
                    if rule.category == "Math":
                        if rule.severity in [Severity.BLOCKER, Severity.ERROR]:
                            math_failed = True
                        else:
                            math_warn = True
                    elif rule.category == "GST":
                        gst_failed = True
            except Exception as e:
                res = RuleResult(
                    rule_id=rule.rule_id,
                    rule_name=rule.rule_name,
                    passed=False,
                    status="FAIL",
                    severity=rule.severity,
                    reason=f"Execution error: {str(e)}",
                    evidence={},
                    recommendation="Inspect system validator logs.",
                    execution_time_ms=0.0
                )
                evaluated_results[rule.rule_id] = res
                failed_rule_ids.add(rule.rule_id)
                errors.append(f"[{rule.rule_id}] Validator exception: {str(e)}")
                
        # Compute sub-statuses
        math_status = "FAILED" if math_failed else ("WARNING" if math_warn else "PASSED")
        gst_status = "FAILED" if gst_failed else "PASSED"
        
        # Deduct compliance score
        score = 100.0
        for res in evaluated_results.values():
            if not res.passed:
                if res.severity == Severity.BLOCKER:
                    score -= 15.0
                elif res.severity == Severity.ERROR:
                    score -= 8.0
                elif res.severity == Severity.WARNING:
                    score -= 3.0
                else: # INFO
                    score -= 0.5
        score = max(0.0, min(100.0, score))
        
        # Define overall status
        if any(res.severity == Severity.BLOCKER and not res.passed for res in evaluated_results.values()):
            overall_status = "BLOCKED"
        elif score < 92.0 or any(res.severity == Severity.ERROR and not res.passed for res in evaluated_results.values()):
            overall_status = "NEEDS_REVIEW"
        else:
            overall_status = "ERP_READY"
            
        execution_time_ms = int((time.time() - t_start) * 1000)
        
        # Map RuleResults to schema-compatible ValidationResults
        validation_results = []
        for r in evaluated_results.values():
            validation_results.append(ValidationResult(
                rule_id=r.rule_id,
                rule_name=r.rule_name,
                category=RuleRegistry.get_rule(r.rule_id).category,
                severity=r.severity.value,
                passed=r.passed,
                status=r.status,
                expected_value=r.evidence.get("expected"),
                actual_value=r.evidence.get("actual"),
                message=r.reason,
                suggested_fix=r.recommendation,
                auto_fix_possible=r.auto_fix,
                execution_time_ms=r.execution_time_ms
            ))
            
        return ValidationReport(
            math_status=math_status,
            gst_status=gst_status,
            overall_status=overall_status,
            overall_score=score,
            total_rules=len(rules),
            errors=errors,
            warnings=warnings,
            passed_rules=list(passed_rule_ids),
            failed_rules=list(failed_rule_ids),
            results=validation_results,
            execution_time_ms=float(execution_time_ms)
        )
