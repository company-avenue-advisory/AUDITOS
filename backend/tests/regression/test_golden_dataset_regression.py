"""
Regression tests for services/golden_dataset.py (Bootstrap Task 5).

No LLM calls, no extraction pipeline touched, no live database required for
the scoring-logic tests -- consistent with every other suite in this
harness ("deterministic layer only"). The seed golden set under
tests/regression/fixtures/golden/ is synthetic (fake GSTINs, fake amounts,
fake invoice numbers) -- no real client documents or PII, by design.

Three groups:
1. Value-comparison and single-case scoring, in isolation.
2. The seed golden set loaded from disk and scored as a whole -- the
   aggregate numbers below are locked exactly like every other regression
   suite locks its expected output, so a change to the scoring logic (or
   an accidental edit to a fixture) is immediately visible.
3. The Bootstrap Task 4 tie-in (annotation_to_golden_field), using a real
   UserAnnotation row via the same in-memory SQLite pattern already used
   in test_review_priority_regression.py.
"""
import sys
import os
import unittest

_backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../backend"))
sys.path.insert(0, _backend_dir)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import Tenant, User, BatchJob, InvoiceTask, TaskStatus, UserAnnotation
from services.golden_dataset import (
    GoldenCase, GoldenField, _values_match,
    score_case, score_golden_set, load_golden_set, load_golden_case_file,
    annotation_to_golden_field,
)

_GOLDEN_FIXTURES_DIR = os.path.join(
    os.path.dirname(__file__), "fixtures", "golden"
)


class TestValuesMatch(unittest.TestCase):

    def test_both_none_matches(self):
        self.assertTrue(_values_match(None, None))

    def test_one_none_does_not_match(self):
        self.assertFalse(_values_match(None, "8471"))
        self.assertFalse(_values_match("8471", None))

    def test_numeric_within_tolerance_matches(self):
        self.assertTrue(_values_match(1000.005, 1000.0))
        self.assertTrue(_values_match("1000.005", 1000.0))  # numeric-as-string coerces

    def test_numeric_outside_tolerance_does_not_match(self):
        self.assertFalse(_values_match(1000.5, 1000.0))

    def test_string_comparison_is_trimmed_and_case_insensitive(self):
        self.assertTrue(_values_match(" Rate Difference ", "Rate Difference"))
        self.assertTrue(_values_match("8471", "8471"))

    def test_string_mismatch(self):
        self.assertFalse(_values_match("8517", "8471"))

    def test_non_numeric_string_against_numeric_expected_does_not_crash(self):
        self.assertFalse(_values_match("not-a-number", 1000.0))


class TestScoreCase(unittest.TestCase):

    def test_all_fields_correct_is_exact_match(self):
        case = GoldenCase(
            case_id="c1", document_type="purchase_invoice", source="synthetic",
            fields={
                "hsn": GoldenField(extracted_value="8471", expected_value="8471"),
                "taxable_value": GoldenField(extracted_value=1000.0, expected_value=1000.0),
            },
        )
        report = score_case(case)
        self.assertTrue(report["exact_match"])
        self.assertEqual(report["field_accuracy"], 1.0)
        self.assertEqual(report["mismatched_fields"], [])

    def test_partial_mismatch_reports_correct_fields_and_names(self):
        case = GoldenCase(
            case_id="c2", document_type="purchase_invoice", source="synthetic",
            fields={
                "hsn": GoldenField(extracted_value="8517", expected_value="8471"),
                "taxable_value": GoldenField(extracted_value=1000.0, expected_value=1000.0),
            },
        )
        report = score_case(case)
        self.assertFalse(report["exact_match"])
        self.assertEqual(report["field_accuracy"], 0.5)
        self.assertEqual(report["mismatched_fields"], ["hsn"])

    def test_case_with_no_fields_is_trivially_exact_match(self):
        case = GoldenCase(case_id="empty", document_type="unknown", source="synthetic", fields={})
        report = score_case(case)
        self.assertTrue(report["exact_match"])
        self.assertEqual(report["total_fields"], 0)


class TestScoreGoldenSet(unittest.TestCase):

    def test_empty_set_returns_perfect_score_and_zero_counts(self):
        result = score_golden_set([])
        self.assertEqual(result["total_cases"], 0)
        self.assertEqual(result["document_level_accuracy"], 1.0)
        self.assertEqual(result["field_level_accuracy"], 1.0)

    def test_by_field_name_breakdown_is_per_field_not_blended(self):
        cases = [
            GoldenCase("c1", "purchase_invoice", "synthetic", {
                "hsn": GoldenField("8517", "8471"),  # wrong every time
                "taxable_value": GoldenField(100.0, 100.0),  # right every time
            }),
            GoldenCase("c2", "purchase_invoice", "synthetic", {
                "hsn": GoldenField("8517", "8471"),  # wrong every time
                "taxable_value": GoldenField(200.0, 200.0),  # right every time
            }),
        ]
        result = score_golden_set(cases)
        self.assertEqual(result["by_field_name"]["hsn"], 0.0)
        self.assertEqual(result["by_field_name"]["taxable_value"], 1.0)


class TestSeedGoldenSetOnDisk(unittest.TestCase):
    """
    Locks the aggregate numbers for the committed synthetic fixture set,
    exactly the way every other regression suite locks its expected
    output. If this test's numbers change, either the fixtures changed
    (intentional -- update the locked numbers) or the scoring logic
    changed (a real regression -- investigate before updating anything).
    """

    def setUp(self):
        self.cases = load_golden_set(_GOLDEN_FIXTURES_DIR)

    def test_seed_set_loads_all_four_fixtures(self):
        self.assertEqual(len(self.cases), 4)
        self.assertEqual(
            sorted(c.case_id for c in self.cases),
            [
                "credit_note_001_rounding_tolerance",
                "purchase_001_exact_match",
                "purchase_002_hsn_and_taxable_mismatch",
                "sales_001_exact_match",
            ],
        )

    def test_seed_set_aggregate_accuracy_is_locked(self):
        result = score_golden_set(self.cases)
        self.assertEqual(result["total_cases"], 4)
        self.assertEqual(result["exact_match_cases"], 3)   # all but purchase_002
        self.assertEqual(result["document_level_accuracy"], 0.75)
        self.assertEqual(result["total_fields"], 21)        # 6 + 6 + 5 + 4
        self.assertEqual(result["correct_fields"], 18)       # 6 + 3 + 5 + 4
        self.assertEqual(result["field_level_accuracy"], 0.8571)

    def test_purchase_002_is_the_only_case_with_mismatches(self):
        result = score_golden_set(self.cases)
        mismatch_cases = [c for c in result["cases"] if not c["exact_match"]]
        self.assertEqual(len(mismatch_cases), 1)
        self.assertEqual(mismatch_cases[0]["case_id"], "purchase_002_hsn_and_taxable_mismatch")
        self.assertEqual(
            sorted(mismatch_cases[0]["mismatched_fields"]),
            ["hsn", "igst_amount", "taxable_value"],
        )

    def test_hsn_field_is_the_lowest_accuracy_field_across_the_seed_set(self):
        # hsn is wrong in exactly one of two cases that have it (purchase_001,
        # purchase_002) -- confirms per-field breakdown surfaces the specific
        # weak field rather than only a blended document-level number.
        result = score_golden_set(self.cases)
        self.assertEqual(result["by_field_name"]["hsn"], 0.5)

    def test_rounding_and_string_normalization_fixture_is_exact_match(self):
        credit_note = next(c for c in self.cases if c.case_id == "credit_note_001_rounding_tolerance")
        report = score_case(credit_note)
        self.assertTrue(report["exact_match"])

    def test_load_single_case_file_directly(self):
        path = os.path.join(_GOLDEN_FIXTURES_DIR, "sales_001_exact_match.json")
        case = load_golden_case_file(path)
        self.assertEqual(case.case_id, "sales_001_exact_match")
        self.assertEqual(case.document_type, "sales_invoice")
        self.assertIn("buyer_gstin", case.fields)


class TestAnnotationToGoldenField(unittest.TestCase):
    """Bootstrap Task 4 tie-in: a real UserAnnotation row converts cleanly."""

    def setUp(self):
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.db.add(Tenant(id="t1", name="OneStack", slug="onestack"))
        self.db.add(User(id="u1", email="reviewer@example.com", hashed_password="x", tenant_id="t1"))
        self.db.add(BatchJob(id="b1", tenant_id="t1", status=TaskStatus.COMPLETED))
        self.db.add(InvoiceTask(id="task1", batch_id="b1", file_name="invoice.pdf", status=TaskStatus.COMPLETED))
        self.db.commit()

    def test_converts_real_correction_row_into_a_golden_field(self):
        annotation = UserAnnotation(
            user_id="u1", task_id="task1", field_name="taxable_value",
            original_value="1000.0", corrected_value="900.0",
            confidence_before=0.55,
        )
        self.db.add(annotation)
        self.db.commit()

        field_name, golden_field = annotation_to_golden_field(annotation)
        self.assertEqual(field_name, "taxable_value")
        self.assertEqual(golden_field.extracted_value, "1000.0")
        self.assertEqual(golden_field.expected_value, "900.0")
        self.assertEqual(golden_field.confidence, 0.55)

        # And it composes directly with score_case, unchanged.
        case = GoldenCase("from_annotation", "purchase_invoice", "reviewer_correction",
                           fields={field_name: golden_field})
        report = score_case(case)
        self.assertFalse(report["exact_match"])  # extracted 1000.0 != corrected 900.0


if __name__ == "__main__":
    unittest.main()
