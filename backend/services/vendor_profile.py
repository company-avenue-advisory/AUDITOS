"""
VendorProfileService — loads JSON profiles from data/vendor_profiles/
and injects format hints into LLM prompts when a known vendor is detected.
"""
import os, json, re, glob
from typing import Optional

_PROFILE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "vendor_profiles")


def _load_profiles() -> list[dict]:
    profiles = []
    if not os.path.isdir(_PROFILE_DIR):
        return profiles
    for path in glob.glob(os.path.join(_PROFILE_DIR, "*.json")):
        if path.endswith("_golden.json"):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                profiles.append(json.load(f))
        except Exception:
            pass
    return profiles


class VendorProfileService:
    def __init__(self):
        self._profiles = _load_profiles()

    def detect(self, full_text: str) -> Optional[dict]:
        """
        Returns the first vendor profile that matches the invoice text.
        Priority: GSTIN match > invoice number prefix match.
        """
        text_upper = full_text.upper()
        for profile in self._profiles:
            gstin = (profile.get("gstin") or "").upper()
            if gstin and gstin in text_upper:
                return profile
        for profile in self._profiles:
            raw_prefix = profile.get("invoice_number_prefix") or ""
            # invoice_number_prefix may be a string or a list of strings
            prefixes = raw_prefix if isinstance(raw_prefix, list) else [raw_prefix]
            if any(p and p.upper() in text_upper for p in prefixes):
                return profile
        return None

    def build_prompt_hints(self, profile: dict, invoice_text: str = "") -> str:
        """
        Returns a short hint block to prepend to item/metadata extraction prompts.
        """
        if not profile:
            return ""
        lines = [f"[KNOWN VENDOR: {profile.get('name', '')} | GSTIN: {profile.get('gstin', '')}]"]
        for hint in profile.get("prompt_hints", []):
            lines.append(f"- {hint}")

        examples = profile.get("few_shot_examples", [])
        if examples:
            lines.append("Examples from this vendor's invoices:")
            for ex in examples[:2]:
                out = ex.get("output", {})
                lines.append(
                    f"  [{ex.get('invoice_type', '?')}] "
                    f"{out.get('particulars', '')} → "
                    f"taxable={out.get('taxable_value')}, "
                    f"cgst={out.get('cgst_amount')}, sgst={out.get('sgst_amount')}, "
                    f"igst={out.get('igst_amount')}, category={out.get('gstr1_category')}"
                )
        return "\n".join(lines)
