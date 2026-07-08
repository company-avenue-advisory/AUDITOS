"""
Finds GSTR-2B JSON files dropped in a tenant's Drive gstr2b_root_folder_id
(see drive_path_resolver.TenantDrivePath) - Phase A automation (this
session, 2026-07-08): someone (the client or their accountant) still
downloads the GSTR-2B JSON from the GST portal by hand each month and
drops it into this folder, since no GSP/portal-API integration exists
yet (that's a separate vendor/business decision, deferred as Phase B -
see conversation this session on GSP pricing). This module removes the
"manually paste JSON into an API call" step (main.py's ReconcileRequest
previously required that), not the "manually download from the portal"
step.

Unlike Sales/Purchase, a GSTR-2B month folder is expected flat - one or
two .json files directly inside it (one per OneStack GST registration),
no subfolder nesting - it's a hand-picked drop location, not a folder
tree synced from anywhere.
"""
import logging
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)

FOLDER_MIME = "application/vnd.google-apps.folder"


def extract_recipient_gstin(raw: dict) -> Optional[str]:
    """
    The GSTIN this GSTR-2B statement was issued FOR (one of OneStack's
    own registrations, e.g. 27AADCO0061H1ZQ or 06AADCO0061H1ZU) - tries
    the common top-level key shapes the GST portal / GSPs actually use.
    Returns None (not a guess) if not found - never assumed from
    filename, matching this codebase's established convention that
    document identity always comes from content, never a name (see
    drive_classifier.py's module docstring for the same principle
    applied to Sales/Purchase documents).
    """
    if not isinstance(raw, dict):
        return None
    candidates = [
        raw.get("gstin"),
        (raw.get("data") or {}).get("gstin") if isinstance(raw.get("data"), dict) else None,
        (raw.get("docdata") or {}).get("gstin") if isinstance(raw.get("docdata"), dict) else None,
    ]
    for c in candidates:
        if c and len(str(c).strip()) >= 15:
            return str(c).strip().upper()
    return None


def list_gstr2b_json_files(list_children_fn: Callable[[str], List[dict]], folder_id: str) -> List[dict]:
    """Every .json file directly inside a GSTR-2B month folder."""
    return [
        f for f in list_children_fn(folder_id)
        if f.get("mimeType") != FOLDER_MIME and f["name"].lower().endswith(".json")
    ]
