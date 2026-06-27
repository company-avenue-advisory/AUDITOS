import unittest
from backend.core.reconciliation.semantic_columns import SemanticColumnClassifier
from backend.core.reconciliation.candidate_scoring import CandidateScorer, EvidenceItem
from backend.core.reconciliation.hsn_guardrails import HSNGuardrail
from backend.core.reconciliation.tax_math import TaxMathematicsEngine
from backend.core.reconciliation.taxable_reconciler import DualStateTaxableReconciler
from backend.core.reconciliation.variance_classifier import VarianceClassifier
from backend.core.reconciliation.correction_engine import CorrectionEngine
from backend.core.reconciliation.memory_features import LayoutMemory

class TestAdvancedReconciliation(unittest.TestCase):

    def test_stage1_semantic_columns(self):
        classifier = SemanticColumnClassifier()
        headers = ["particulars", "hsn/sac", "qty", "taxable value", "cgst amount"]
        res = classifier.classify_columns(headers)
        self.assertEqual(res["particulars"], "DESCRIPTION")
        self.assertEqual(res["hsn/sac"], "HSN")
        self.assertEqual(res["qty"], "QTY")
        self.assertEqual(res["taxable value"], "TAXABLE")
        self.assertEqual(res["cgst amount"], "CGST")

    def test_stage2_candidate_scoring(self):
        scorer = CandidateScorer()
        evidence = [
            EvidenceItem("header", "Matches taxable column header", 0.3, 0.0),
            EvidenceItem("pattern", "Non-HSN pattern matching", 0.1, 0.0)
        ]
        res = scorer.score_candidate(15000.0, evidence)
        self.assertGreater(res["score"], 0.5)

    def test_stage3_hsn_guardrail(self):
        guardrail = HSNGuardrail()
        # Should flag 4, 6, 8 digit values
        res1 = guardrail.validate_guardrail(9971.0, "9971", "HSN")
        self.assertTrue(res1["rejected"])
        self.assertEqual(res1["score_penalty"], 1.0)
        
        # Valid taxable amount
        res2 = guardrail.validate_guardrail(15250.0, "9971", "TAXABLE")
        self.assertFalse(res2["rejected"])

    def test_stage4_tax_math(self):
        engine = TaxMathematicsEngine()
        data = {
            "taxable": 100.0,
            "cgst": 9.0,
            "sgst": 9.0,
            "igst": 0.0,
            "total": 118.0
        }
        res = engine.evaluate_paths(data)
        self.assertEqual(res["winning_path"], "Path A")
        self.assertTrue(res["verified"])

    def test_stage5_dual_state_taxable(self):
        reconciler = DualStateTaxableReconciler()
        res = reconciler.reconcile_dual_state(summary_taxable=7500.0, gross_taxable=10000.0, discount=2500.0)
        self.assertEqual(res["classification"], "NET_BASED")
        self.assertTrue(res["reconciliation_metadata"]["is_net_based"])

    def test_stage6_variance_classifier(self):
        classifier = VarianceClassifier()
        res = classifier.classify_variance(["taxable_value"], 2500.0, {"is_discount_match": True})
        self.assertEqual(res["category"], "GLOBAL_DISCOUNT")

    def test_stage7_correction_proposal(self):
        engine = CorrectionEngine()
        proposal = engine.generate_proposal(
            field_name="taxable_value",
            original=10000.0,
            suggested=7500.0,
            reason="Discount adjustment",
            evidence=[{"type": "discount_match"}],
            category="GLOBAL_DISCOUNT"
        )
        self.assertEqual(proposal["field"], "taxable_value")
        self.assertEqual(proposal["proposal"]["suggested_value"], 7500.0)

    def test_stage8_layout_memory(self):
        memory = LayoutMemory()
        headers = ["particulars", "hsn", "amount"]
        coords = [10.0, 50.0, 100.0]
        
        mapping = {"particulars": "DESCRIPTION", "hsn": "HSN", "amount": "TAXABLE"}
        fingerprint = memory.store_layout("One Stack", headers, coords, mapping, "Path A")
        
        lookup = memory.lookup_layout(headers, coords)
        self.assertEqual(lookup["vendor"], "One Stack")
        self.assertEqual(lookup["accepted_path"], "Path A")
