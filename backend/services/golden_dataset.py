"""
Golden Dataset & Regression Framework (Bootstrap Task 5).

Reviewed before writing: the existing regression suites (test_reconciliation_regression.py,
test_validation_regression.py, etc.) already lock deterministic-engine behavior against
hand-built CanonicalInvoice fixtures, and run_regression.py's own docstring is explicit --
"deterministic layer only, no LLM calls." This module does not touch or re-run extraction;
it does not call any LLM, OCR provider, or the extraction pipeline in core/extraction/ at
all. It grades a static, versioned set of (what was extracted, what was actually correct)
field pairs -- the "golden dataset" -- the same way every other regression suite grades a
static, versioned set of inputs against a locked expected output. Re-running live
extraction against real documents on a schedule is a separate, future concern (the
"monthly CA-grading process" from the engineering blueprint); this module is the grading
math and the format that process will eventually feed, built and tested now so it isn't
retrofitted later.

No real client documents or PII are used or required. Golden cases are field-level data
points: (case_id, field_name) -> (extracted_value, expected_value[, confidence]). They can
come from hand-built synthetic fixtures (this module ships a small seed set) or, later,
from real reviewer corrections -- Bootstrap Task 4's UserAnnotation table already has
exactly this shape, and annotation_to_golden_field() below converts one row into one golden
data point, on demand, never automatically -- nothing in this module reads the database or
schedules anything.
"""
import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ── Data model ────────────────────────────────────────────────────────────

@dataclass
class GoldenField:
    """One field-level data point: what was extracted vs. what was actually correct."""
    extracted_value: Any
    expected_value: Any
    confidence: Optional[float] = None  # extraction confidence at the time, if known


@dataclass
class GoldenCase:
    """One document's worth of golden field data points."""
    case_id: str
    document_type: str                      # e.g. "purchase_invoice", "sales_invoice", "credit_note"
    source: str                             # "synthetic" | "reviewer_correction" | ...
    fields: Dict[str, GoldenField] = field(default_factory=dict)


# ── Value comparison ─────────────────────────────────────────────────────

NUMERIC_TOLERANCE = 0.01  # absolute tolerance for float/amount comparisons, in the field's own unit


def _values_match(extracted: Any, expected: Any) -> bool:
    """
    Field-level match rule shared by every case. Deliberately simple and
    explainable -- this is grading logic, not a model, and every rule here
    should be auditable at a glance:
      - None/empty on both sides counts as a match (nothing was expected, nothing was extracted)
      - numeric values compare within NUMERIC_TOLERANCE (rounding differences are not errors)
      - everything else compares as a normalized (trimmed, case-insensitive) string
    """
    if extracted is None and expected is None:
        return True
    if extracted is None or expected is None:
        return False

    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        try:
            return abs(float(extracted) - float(expected)) <= NUMERIC_TOLERANCE
        except (TypeError, ValueError):
            return False

    return str(extracted).strip().casefold() == str(expected).strip().casefold()


# ── Scoring ───────────────────────────────────────────────────────────────

def score_case(case: GoldenCase) -> Dict[str, Any]:
    """Field-level accuracy report for a single golden case."""
    total = len(case.fields)
    if total == 0:
        return {
            "case_id": case.case_id, "document_type": case.document_type,
            "total_fields": 0, "correct_fields": 0, "field_accuracy": 1.0,
            "exact_match": True, "mismatched_fields": [],
        }

    mismatched = [
        name for name, f in case.fields.items()
        if not _values_match(f.extracted_value, f.expected_value)
    ]
    correct = total - len(mismatched)

    return {
        "case_id": case.case_id,
        "document_type": case.document_type,
        "total_fields": total,
        "correct_fields": correct,
        "field_accuracy": round(correct / total, 4),
        "exact_match": len(mismatched) == 0,
        "mismatched_fields": mismatched,
    }


def score_golden_set(cases: List[GoldenCase]) -> Dict[str, Any]:
    """
    Aggregate accuracy across a whole golden set, plus a per-field-name
    breakdown (which specific fields are the most error-prone across the
    set -- the signal that actually tells you where to spend engineering
    effort, not just a single blended pass/fail number).
    """
    if not cases:
        return {
            "total_cases": 0, "exact_match_cases": 0, "document_level_accuracy": 1.0,
            "total_fields": 0, "correct_fields": 0, "field_level_accuracy": 1.0,
            "by_field_name": {}, "cases": [],
        }

    case_reports = [score_case(c) for c in cases]

    total_fields = sum(r["total_fields"] for r in case_reports)
    correct_fields = sum(r["correct_fields"] for r in case_reports)
    exact_match_cases = sum(1 for r in case_reports if r["exact_match"])

    by_field_name: Dict[str, Dict[str, int]] = {}
    for c in cases:
        for name, f in c.fields.items():
            bucket = by_field_name.setdefault(name, {"total": 0, "correct": 0})
            bucket["total"] += 1
            if _values_match(f.extracted_value, f.expected_value):
                bucket["correct"] += 1

    by_field_accuracy = {
        name: round(b["correct"] / b["total"], 4) if b["total"] else 1.0
        for name, b in by_field_name.items()
    }

    return {
        "total_cases": len(cases),
        "exact_match_cases": exact_match_cases,
        "document_level_accuracy": round(exact_match_cases / len(cases), 4),
        "total_fields": total_fields,
        "correct_fields": correct_fields,
        "field_level_accuracy": round(correct_fields / total_fields, 4) if total_fields else 1.0,
        "by_field_name": by_field_accuracy,
        "cases": case_reports,
    }


# ── Fixture loading ──────────────────────────────────────────────────────

def load_golden_case_file(file_path: str) -> GoldenCase:
    """
    Loads one golden case from a JSON fixture file. Expected shape:
    {
      "case_id": "purchase_001",
      "document_type": "purchase_invoice",
      "source": "synthetic",
      "fields": {
        "taxable_value": {"extracted": 1000.0, "expected": 1000.0, "confidence": 0.95},
        "hsn":           {"extracted": "8471",  "expected": "8517", "confidence": 0.70}
      }
    }
    """
    with open(file_path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)

    fields = {
        name: GoldenField(
            extracted_value=spec.get("extracted"),
            expected_value=spec.get("expected"),
            confidence=spec.get("confidence"),
        )
        for name, spec in raw.get("fields", {}).items()
    }
    return GoldenCase(
        case_id=raw["case_id"],
        document_type=raw.get("document_type", "unknown"),
        source=raw.get("source", "unknown"),
        fields=fields,
    )


def load_golden_set(directory: str) -> List[GoldenCase]:
    """Loads every *.json golden case file in a directory, sorted by filename
    for deterministic ordering (matters for reproducible regression runs)."""
    if not os.path.isdir(directory):
        return []
    filenames = sorted(f for f in os.listdir(directory) if f.endswith(".json"))
    return [load_golden_case_file(os.path.join(directory, f)) for f in filenames]


# ── Bootstrap Task 4 tie-in: correction events -> golden data points ────────

def annotation_to_golden_field(annotation) -> Tuple[str, GoldenField]:
    """
    Converts one UserAnnotation correction row (Bootstrap Task 4) into one
    (field_name, GoldenField) data point: original_value is what was
    extracted, corrected_value is what a reviewer verified as correct.

    Deliberately a single-row converter, not a database-reading pipeline --
    nothing in this module queries the DB or decides when/whether a
    correction should enter the golden set. Grouping several annotations
    for the same task into one GoldenCase, deciding a retention/promotion
    policy, and any scheduling of that process are explicitly out of scope
    here (per RFC-002's differentiated-verification-checkpoint doctrine, a
    raw correction is a proposal, not yet golden-set-worthy, until an
    explicit promotion step -- which this function is one building block
    of, not the whole thing).
    """
    return annotation.field_name, GoldenField(
        extracted_value=annotation.original_value,
        expected_value=annotation.corrected_value,
        confidence=annotation.confidence_before,
    )
