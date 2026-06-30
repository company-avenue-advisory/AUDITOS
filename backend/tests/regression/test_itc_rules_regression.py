"""
Regression tests for Section 17(5) ITC eligibility rules (_apply_itc_rules).

These are the hard-block deterministic overrides that must never change
without an explicit CA review. Any regression here means incorrect ITC
claims could reach the GSTR-3B filing.

Covers:
  - HSN-based hard blocks (motor vehicles, motorcycles, beauty)
  - Keyword-based hard blocks (club membership, health insurance, etc.)
  - LLM output normalisation (ELIGIBLE / FULL_ITC / YES → ITC_ELIGIBLE)
  - Items not in blocked lists remain ITC_ELIGIBLE
  - Blocked reason string is populated correctly
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from backend.core.extraction.extractor.item_extractor import (
    _apply_itc_rules,
    ITC_ELIGIBLE,
    ITC_BLOCKED,
    ITC_RESTRICTED,
    ITC_EXEMPT,
    ITC_UNKNOWN,
    _SEC_17_5_HSN_PREFIXES,
    _SEC_17_5_BLOCKED_KEYWORDS,
)


def _item(hsn="", particulars="", itc_category="ITC_ELIGIBLE"):
    return {"hsn": hsn, "particulars": particulars, "itc_category": itc_category}


class TestHSNHardBlocks(unittest.TestCase):
    """Every HSN in Section 17(5) must be blocked regardless of LLM output."""

    def _assert_blocked(self, hsn: str):
        items = [_item(hsn=hsn, itc_category="ITC_ELIGIBLE")]
        result = _apply_itc_rules(items)
        self.assertEqual(
            result[0]["itc_category"], ITC_BLOCKED,
            f"HSN {hsn} must be hard-blocked by Section 17(5)"
        )
        self.assertIn("itc_block_reason", result[0])

    def test_motor_vehicle_8703_blocked(self):
        self._assert_blocked("8703")

    def test_motor_vehicle_8703xx_prefix_blocked(self):
        # Full HSN with sub-codes
        self._assert_blocked("87032300")

    def test_motorcycle_8711_blocked(self):
        self._assert_blocked("8711")

    def test_trailer_8716_blocked(self):
        self._assert_blocked("8716")

    def test_beauty_3303_blocked(self):
        self._assert_blocked("3303")

    def test_beauty_3304_blocked(self):
        self._assert_blocked("3304")

    def test_beauty_3305_blocked(self):
        self._assert_blocked("3305")

    def test_beauty_3306_blocked(self):
        self._assert_blocked("3306")

    def test_beauty_3307_blocked(self):
        self._assert_blocked("3307")

    def test_all_sec_17_5_prefixes_covered(self):
        """Smoke-test: every prefix in the constant is actually blocked."""
        for pfx in _SEC_17_5_HSN_PREFIXES:
            items = [_item(hsn=pfx, itc_category="ITC_ELIGIBLE")]
            result = _apply_itc_rules(items)
            self.assertEqual(result[0]["itc_category"], ITC_BLOCKED, f"Prefix {pfx} not blocked")

    def test_eligible_hsn_not_blocked(self):
        """Stationery HSN 4820 must remain eligible."""
        items = [_item(hsn="4820", itc_category="ITC_ELIGIBLE")]
        result = _apply_itc_rules(items)
        self.assertEqual(result[0]["itc_category"], ITC_ELIGIBLE)
        self.assertNotIn("itc_block_reason", result[0])


class TestKeywordHardBlocks(unittest.TestCase):
    """Service description keywords that trigger Section 17(5) block."""

    def _assert_keyword_blocked(self, particulars: str):
        items = [_item(particulars=particulars, itc_category="ITC_ELIGIBLE")]
        result = _apply_itc_rules(items)
        self.assertEqual(
            result[0]["itc_category"], ITC_BLOCKED,
            f"Keyword in '{particulars}' must be hard-blocked"
        )

    def test_club_membership_blocked(self):
        self._assert_keyword_blocked("Annual Club Membership Fee")

    def test_health_club_blocked(self):
        self._assert_keyword_blocked("Health Club subscription")

    def test_fitness_blocked(self):
        self._assert_keyword_blocked("Fitness Centre charges")

    def test_beauty_treatment_blocked(self):
        self._assert_keyword_blocked("Beauty Treatment Services")

    def test_cosmetic_surgery_blocked(self):
        self._assert_keyword_blocked("Cosmetic Surgery expenses")

    def test_outdoor_catering_blocked(self):
        self._assert_keyword_blocked("Outdoor Catering for annual day event")

    def test_rent_a_cab_blocked(self):
        self._assert_keyword_blocked("Rent a cab service for employees")

    def test_life_insurance_blocked(self):
        self._assert_keyword_blocked("Life Insurance premium")

    def test_health_insurance_blocked(self):
        self._assert_keyword_blocked("Health Insurance Group policy")

    def test_works_contract_immovable_blocked(self):
        self._assert_keyword_blocked("Works contract for immovable property construction")

    def test_construction_immovable_blocked(self):
        self._assert_keyword_blocked("Construction of immovable structure")

    def test_all_keywords_covered(self):
        """Every keyword in the constant must trigger a block."""
        for kw in _SEC_17_5_BLOCKED_KEYWORDS:
            items = [_item(particulars=kw, itc_category="ITC_ELIGIBLE")]
            result = _apply_itc_rules(items)
            self.assertEqual(result[0]["itc_category"], ITC_BLOCKED, f"Keyword '{kw}' not blocked")

    def test_non_blocked_service_eligible(self):
        items = [_item(particulars="Office stationery purchase", itc_category="ITC_ELIGIBLE")]
        result = _apply_itc_rules(items)
        self.assertEqual(result[0]["itc_category"], ITC_ELIGIBLE)


class TestLLMOutputNormalisation(unittest.TestCase):
    """LLM returns varied string forms — all must normalise correctly."""

    def _normalise(self, raw: str) -> str:
        items = [_item(itc_category=raw)]
        return _apply_itc_rules(items)[0]["itc_category"]

    def test_eligible_variants(self):
        for raw in ("ELIGIBLE", "FULL_ITC", "YES", "Y", "ALLOWED", "ITC_ELIGIBLE"):
            self.assertEqual(self._normalise(raw), ITC_ELIGIBLE, f"'{raw}' not normalised to ITC_ELIGIBLE")

    def test_blocked_variants(self):
        for raw in ("BLOCKED", "NOT_ELIGIBLE", "NO", "N", "INELIGIBLE", "ITC_BLOCKED"):
            self.assertEqual(self._normalise(raw), ITC_BLOCKED, f"'{raw}' not normalised to ITC_BLOCKED")

    def test_restricted_variants(self):
        for raw in ("RESTRICTED", "PARTIAL", "PRO_RATA", "ITC_RESTRICTED"):
            self.assertEqual(self._normalise(raw), ITC_RESTRICTED, f"'{raw}' not normalised to ITC_RESTRICTED")

    def test_exempt_variants(self):
        for raw in ("EXEMPT", "NIL_RATED", "ITC_EXEMPT"):
            self.assertEqual(self._normalise(raw), ITC_EXEMPT, f"'{raw}' not normalised to ITC_EXEMPT")

    def test_unknown_becomes_unknown(self):
        for raw in ("UNCLEAR", "", None, "MAYBE", "0"):
            items = [_item(itc_category=raw)]
            result = _apply_itc_rules(items)[0]["itc_category"]
            self.assertEqual(result, ITC_UNKNOWN, f"'{raw}' must become ITC_UNKNOWN")


class TestHSNTakesPrecedenceOverKeyword(unittest.TestCase):
    """HSN block is checked before keyword — blocked HSN wins even if particulars are benign."""

    def test_blocked_hsn_overrides_eligible_keyword(self):
        items = [_item(hsn="8703", particulars="Office furniture delivery", itc_category="ITC_ELIGIBLE")]
        result = _apply_itc_rules(items)
        self.assertEqual(result[0]["itc_category"], ITC_BLOCKED)
        self.assertIn("HSN", result[0]["itc_block_reason"])

    def test_eligible_hsn_with_blocked_keyword_still_blocked(self):
        items = [_item(hsn="9993", particulars="Club membership for staff", itc_category="ITC_ELIGIBLE")]
        result = _apply_itc_rules(items)
        self.assertEqual(result[0]["itc_category"], ITC_BLOCKED)


class TestMixedBatch(unittest.TestCase):
    """A batch with mixed ITC items — each processed independently."""

    def test_mixed_batch_correct_outcomes(self):
        batch = [
            _item(hsn="4820", particulars="Stationery", itc_category="ITC_ELIGIBLE"),   # eligible
            _item(hsn="8703", particulars="Car for directors", itc_category="ITC_ELIGIBLE"),  # blocked by HSN
            _item(hsn="9993", particulars="Club membership", itc_category="ITC_ELIGIBLE"),    # blocked by keyword
            _item(hsn="8479", particulars="Industrial machinery", itc_category="ITC_ELIGIBLE"),  # eligible
        ]
        result = _apply_itc_rules(batch)
        self.assertEqual(result[0]["itc_category"], ITC_ELIGIBLE)
        self.assertEqual(result[1]["itc_category"], ITC_BLOCKED)
        self.assertEqual(result[2]["itc_category"], ITC_BLOCKED)
        self.assertEqual(result[3]["itc_category"], ITC_ELIGIBLE)

    def test_batch_returns_same_length(self):
        batch = [_item() for _ in range(10)]
        result = _apply_itc_rules(batch)
        self.assertEqual(len(result), 10)


if __name__ == "__main__":
    unittest.main(verbosity=2)
