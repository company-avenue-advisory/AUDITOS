"""
Resolves a tenant's Drive path config (data/drive_paths/{slug}.json) plus a
target date into the actual month-folder ID to hand to drive_classifier.

The month folder's own Drive ID changes every month and can never be
hardcoded - only the parent root ID is stable. So resolution always means
"list the root folder's children and find the one whose name matches this
month's computed pattern", never "assume an ID".

fiscal_year_start_month=4 (April, per OneStack's real folders: '1. April
2026' through '4. July 2026' confirmed in Drive) means month position N
resets every April: April=1, May=2, ..., March=12.
"""

import json
import os
from calendar import month_name
from dataclasses import dataclass
from datetime import date
from typing import Callable, List, Optional

_CONFIG_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "drive_paths")


@dataclass
class TenantDrivePath:
    tenant_slug: str
    fiscal_year_start_month: int
    sales_root_folder_id: Optional[str]
    purchase_root_folder_id: Optional[str]
    month_folder_pattern: str
    sales_subfolder_map: dict
    root_file_rule: dict
    gstr2b_root_folder_id: Optional[str] = None


# Defaults applied when a tenant hasn't customized these via the DB-backed
# config - matches OneStack's real, confirmed folder-naming convention.
# Not yet exposed in the Drive Sync UI (see load_tenant_path_config_from_db's
# docstring); a tenant with a differently-named folder tree still needs a
# code change until that's built out.
_DEFAULT_MONTH_FOLDER_PATTERN = "{n}. {month_name} {year}"
_DEFAULT_SALES_SUBFOLDER_MAP = {
    "sales invoice": "invoice",
    "other invoices": "invoice",
    "credit note": "credit_note",
    "sale analysis": "ignore",
}
_DEFAULT_ROOT_FILE_RULE = {"xlsx": "client_sheet", "xls": "client_sheet", "pdf": "invoice"}


def load_tenant_path_config(tenant_slug: str) -> TenantDrivePath:
    path = os.path.join(_CONFIG_DIR, f"{tenant_slug}.json")
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    return TenantDrivePath(
        tenant_slug=cfg["tenant_slug"],
        fiscal_year_start_month=cfg["fiscal_year_start_month"],
        sales_root_folder_id=cfg["sales_root_folder_id"],
        purchase_root_folder_id=cfg.get("purchase_root_folder_id"),
        month_folder_pattern=cfg["month_folder_pattern"],
        sales_subfolder_map=cfg["sales_subfolder_map"],
        root_file_rule=cfg["root_file_rule"],
        gstr2b_root_folder_id=cfg.get("gstr2b_root_folder_id"),
    )


def load_tenant_path_config_from_db(cfg, tenant_slug: str) -> TenantDrivePath:
    """
    Builds a TenantDrivePath from a models.GoogleDriveSyncConfig row instead
    of a hand-edited data/drive_paths/<slug>.json file - added 2026-07-09 so
    any tenant can configure Sales/Purchase/GSTR-2B self-resolving ingestion
    from the Drive Sync UI (POST /api/google-drive-sync/config) rather than
    needing someone to create and edit a JSON file on the server, which
    only ever worked for OneStack (the one tenant that got one by hand).

    sales_subfolder_map/root_file_rule aren't yet per-tenant customizable
    fields in the DB config - they use the same defaults confirmed against
    OneStack's real folder tree. A tenant with a differently-organized
    Drive tree still needs those fields added to the DB schema and UI
    before this fully generalizes; tracked as a known gap, not silently
    assumed to work for everyone.

    tenant_slug is passed separately (not read off cfg) since
    GoogleDriveSyncConfig doesn't store it - callers already have the
    Tenant row loaded (that's how they found cfg via tenant_id) and can
    pass its .slug directly.
    """
    return TenantDrivePath(
        tenant_slug=tenant_slug,
        fiscal_year_start_month=cfg.fiscal_year_start_month or 4,
        sales_root_folder_id=cfg.sales_root_folder_id,
        purchase_root_folder_id=cfg.purchase_root_folder_id,
        month_folder_pattern=cfg.month_folder_pattern or _DEFAULT_MONTH_FOLDER_PATTERN,
        sales_subfolder_map=_DEFAULT_SALES_SUBFOLDER_MAP,
        root_file_rule=_DEFAULT_ROOT_FILE_RULE,
        gstr2b_root_folder_id=cfg.gstr2b_root_folder_id,
    )


def fiscal_month_index(target: date, fiscal_year_start_month: int) -> int:
    """1 for the first month of the fiscal year, up to 12."""
    return (target.month - fiscal_year_start_month) % 12 + 1


def expected_month_folder_name(target: date, cfg: TenantDrivePath) -> str:
    n = fiscal_month_index(target, cfg.fiscal_year_start_month)
    return cfg.month_folder_pattern.format(
        n=n, month_name=month_name[target.month], year=target.year
    )


FOLDER_MIME = "application/vnd.google-apps.folder"


def resolve_month_folder_id(
    list_children_fn: Callable[[str], List[dict]],
    cfg: TenantDrivePath,
    target: date,
    root_folder_id: Optional[str] = None,
) -> Optional[str]:
    """
    Looks up this month's folder ID under the given root (defaults to
    cfg.sales_root_folder_id) by matching the computed expected name.
    Returns None if that month's folder doesn't exist yet (e.g. asking
    for next month before anyone has created it) - callers should treat
    that as "nothing to ingest yet", not an error.
    """
    root = root_folder_id or cfg.sales_root_folder_id
    expected_name = expected_month_folder_name(target, cfg)
    for item in list_children_fn(root):
        if item["mimeType"] == FOLDER_MIME and item["name"].strip() == expected_name:
            return item["id"]
    return None
