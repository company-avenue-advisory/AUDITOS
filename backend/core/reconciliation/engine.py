import time
import logging
from typing import Dict, List, Any, Optional
from backend.core.schema import CanonicalInvoice
from backend.core.reconciliation.reports.reconciliation_report import ReconciliationReport
from backend.core.reconciliation.review_context import ReviewContext, ReviewContextItem
from backend.core.reconciliation.evidence import FinancialEvidence, AutoCorrectionSuggestion
from backend.core.reconciliation.state_machine import FinancialState
from backend.core.reconciliation.source_hierarchy import FIELD_SOURCE_AUTHORITY, SourceRank
from backend.core.reconciliation.line_item_reconciler import reconcile_line_items
from backend.core.reconciliation.taxable_reconciler import reconcile_taxable_value, DualStateTaxableReconciler
from backend.core.reconciliation.gst_reconciler import reconcile_gst_logic
from backend.core.reconciliation.totals_reconciler import reconcile_summary_totals
from backend.core.reconciliation.confidence import calculate_field_confidences

# Import new Stage 1-8 modules
from backend.core.reconciliation.semantic_columns import SemanticColumnClassifier
from backend.core.reconciliation.candidate_scoring import CandidateScorer, EvidenceItem
from backend.core.reconciliation.hsn_guardrails import HSNGuardrail
from backend.core.reconciliation.tax_math import TaxMathematicsEngine
from backend.core.reconciliation.variance_classifier import VarianceClassifier
from backend.core.reconciliation.correction_engine import CorrectionEngine
from backend.core.reconciliation.memory_features import LayoutMemory

logger = logging.getLogger("AuditOS.Reconciliation")

class FinancialReconciliationEngine:
    """
    Chartered Accountant reasoning engine that deterministically verifies,
    ranks, wraps and reports on all financial details in a CanonicalInvoice.
    """
    def __init__(self):
        self.classifier = SemanticColumnClassifier()
        self.scorer = CandidateScorer()
        self.guardrail = HSNGuardrail()
        self.math_engine = TaxMathematicsEngine()
        self.dual_state_reconciler = DualStateTaxableReconciler()
        self.variance_classifier = VarianceClassifier()
        self.correction_engine = CorrectionEngine()
        self.layout_memory = LayoutMemory()

    def reconcile(self, invoice: CanonicalInvoice, extra_context: Optional[Dict[str, Any]] = None) -> ReconciliationReport:
        t_start = time.time()
        ctx = extra_context or {}
        
        # 1. Stage 1: Semantic Column Classification
        headers = ctx.get("headers", ["particulars", "hsn", "amount", "total"])
        semantic_columns = self.classifier.classify_columns(headers)
        logger.info(f"semantic_columns_detected: {semantic_columns}")
        
        # 2. Execute Levels 1-3
        lvl1_passed, lvl1_errors, lvl1_trace = reconcile_line_items(invoice)
        lvl2_taxable_passed, lvl2_taxable_errors, lvl2_taxable_trace = reconcile_taxable_value(invoice)
        lvl2_totals_passed, lvl2_totals_errors, lvl2_totals_trace = reconcile_summary_totals(invoice)
        lvl3_passed, lvl3_errors, lvl3_trace = reconcile_gst_logic(invoice)
        
        # 3. Stage 3 & 4: HSN guardrails & Math evaluation
        taxable_val = invoice.tax_summary.taxable_value.value or 0.0
        cgst_val = invoice.tax_summary.cgst_amount.value or 0.0
        sgst_val = invoice.tax_summary.sgst_amount.value or 0.0
        igst_val = invoice.tax_summary.igst_amount.value or 0.0
        cess_val = invoice.tax_summary.cess_amount.value or 0.0
        round_val = invoice.tax_summary.round_off.value or 0.0
        grand_val = invoice.tax_summary.grand_total.value or 0.0
        
        hsn_validation = self.guardrail.validate_guardrail(taxable_val, "9971", "TAXABLE")
        if hsn_validation["rejected"]:
            logger.warning("hsn_candidate_rejected: Taxable value candidate matches HSN.")
            
        math_evaluation = self.math_engine.evaluate_paths({
            "taxable": taxable_val,
            "cgst": cgst_val,
            "sgst": sgst_val,
            "igst": igst_val,
            "total": grand_val
        })
        logger.info(f"tax_path_selected: {math_evaluation['winning_path']}")

        # Collect failed fields
        failed_fields = []
        hierarchical_failures = {
            "Level 1 (Line Items)": lvl1_errors,
            "Level 2 (Summary Taxable)": lvl2_taxable_errors,
            "Level 2 (Summary Totals)": lvl2_totals_errors,
            "Level 3 (Business GST Rules)": lvl3_errors
        }
        
        for k, v in hierarchical_failures.items():
            if v:
                failed_fields.extend(v)
                
        # Calculate confidences
        overall_conf, field_conf = calculate_field_confidences(invoice, [
            "taxable_value" if not lvl2_taxable_passed else "",
            "grand_total" if not lvl2_totals_passed else "",
            "cgst_amount" if not lvl3_passed else "",
            "sgst_amount" if not lvl3_passed else "",
            "igst_amount" if not lvl3_passed else ""
        ])
        
        # Determine overall status
        is_reconciled = lvl1_passed and lvl2_taxable_passed and lvl2_totals_passed and lvl3_passed
        
        # If Level 1 or 2 total check fails, we block or flag
        if not lvl2_totals_passed or not lvl2_taxable_passed:
            status = "BLOCKED"
        elif not is_reconciled:
            status = "NEEDS_REVIEW"
        else:
            status = "ERP_READY"
            
        # Build field evidence map
        evidence_map: Dict[str, FinancialEvidence] = {}
        
        # Helper to wrap evidence
        def wrap_evidence(field: str, ext_val: float, calc_val: float, passed: bool, calc_path: str = None) -> FinancialEvidence:
            state = FinancialState.RECONCILED if passed else FinancialState.NEEDS_REVIEW
            variance = abs(ext_val - calc_val)
            rank = FIELD_SOURCE_AUTHORITY.get(field, SourceRank.LLM_EXTRACTION)
            
            # Stage 2: Evidence Scoring
            evidence_items = [
                EvidenceItem("reconciler", f"Comparison check for {field}", 0.2 if passed else 0.0, 0.0 if passed else 0.3)
            ]
            scored = self.scorer.score_candidate(ext_val, evidence_items)
            
            # Stage 7: Auto-correction Suggestion
            suggestion = None
            if not passed:
                prop = self.correction_engine.generate_proposal(
                    field_name=field,
                    original=ext_val,
                    suggested=calc_val,
                    reason=f"Recalculated {field} matches mathematical layout path.",
                    evidence=scored["evidence"],
                    category="ROUND_OFF" if variance <= 1.5 else "COLUMN_SHIFT"
                )
                logger.info(f"correction_generated: Suggested correction for {field} to {calc_val}")
                suggestion = AutoCorrectionSuggestion(
                    suggested_value=calc_val,
                    reason=prop["proposal"]["explanation"]
                )
                
            return FinancialEvidence(
                value=ext_val,
                calculated_value=calc_val,
                variance=variance,
                confidence=field_conf.get(field, 0.99),
                evidence_score=float(rank),
                source="calculation" if passed else "llm",
                calculation=calc_path,
                verified=passed,
                status_state=state,
                suggested_correction=suggestion
            )
            
        evidence_map["taxable_value"] = wrap_evidence(
            "taxable_value", taxable_val, lvl2_taxable_trace.get("sum_line_taxable", 0.0), lvl2_taxable_passed,
            calc_path="Sum(LineItem.taxable_value)"
        )
        
        evidence_map["grand_total"] = wrap_evidence(
            "grand_total", grand_val, lvl2_totals_trace.get("calculated_total", 0.0), lvl2_totals_passed,
            calc_path="taxable_value + cgst_amount + sgst_amount + igst_amount + cess_amount + round_off"
        )
        
        # Compile Review Context for human review dashboard UI
        review_items: List[ReviewContextItem] = []
        
        if not lvl2_taxable_passed:
            # Stage 6: Variance Classification
            var_class = self.variance_classifier.classify_variance(["taxable_value"], lvl2_taxable_trace.get("variance", 0.0), {})
            logger.warning(f"variance_detected: {var_class['explanation']}")
            
            review_items.append(ReviewContextItem(
                field_name="taxable_value",
                extracted_value=taxable_val,
                calculated_value=lvl2_taxable_trace.get("sum_line_taxable"),
                expected_value=lvl2_taxable_trace.get("sum_line_taxable"),
                variance=lvl2_taxable_trace.get("variance"),
                reason="Taxable sum of line items does not equal summary taxable value.",
                recommendation="Replace overall taxable value with sum of line items taxable values.",
                severity="ERROR",
                failure_category="MATH_ERROR"
            ))
            
        if not lvl2_totals_passed:
            review_items.append(ReviewContextItem(
                field_name="grand_total",
                extracted_value=grand_val,
                calculated_value=lvl2_totals_trace.get("calculated_total"),
                expected_value=lvl2_totals_trace.get("calculated_total"),
                variance=lvl2_totals_trace.get("variance"),
                reason="Summary total calculation mismatch.",
                recommendation="Verify taxes, taxable base values, and round-offs.",
                severity="BLOCKER",
                failure_category="MATH_ERROR"
            ))
            
        review_context = ReviewContext(
            is_blocked=(status == "BLOCKED"),
            items=review_items
        )
        
        # Build calculation trace tree
        calculation_trace = {
            "grand_total": grand_val,
            "calculated_total": lvl2_totals_trace.get("calculated_total"),
            "taxable_value": taxable_val,
            "calculated_taxable": lvl2_taxable_trace.get("sum_line_taxable"),
            "taxes": {
                "cgst": cgst_val,
                "sgst": sgst_val,
                "igst": igst_val,
                "cess": cess_val
            },
            "line_items_traces": lvl1_trace,
            "semantic_columns": semantic_columns,
            "math_evaluation": math_evaluation
        }
        
        execution_time_ms = int((time.time() - t_start) * 1000)
        
        return ReconciliationReport(
            is_reconciled=is_reconciled,
            status=status,
            overall_confidence=overall_conf,
            calculated_taxable=lvl2_taxable_trace.get("sum_line_taxable", 0.0),
            calculated_tax=cgst_val + sgst_val + igst_val + cess_val,
            calculated_total=lvl2_totals_trace.get("calculated_total", 0.0),
            variance_taxable=lvl2_taxable_trace.get("variance", 0.0),
            variance_total=lvl2_totals_trace.get("variance", 0.0),
            failed_fields=failed_fields,
            hierarchical_failures={k: v for k, v in hierarchical_failures.items() if v},
            calculation_trace=calculation_trace,
            field_evidence=evidence_map,
            review_context=review_context,
            execution_time_ms=float(execution_time_ms)
        )
