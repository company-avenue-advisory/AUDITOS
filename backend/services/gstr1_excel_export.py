"""
gstr1_excel_export.py -- Writes a GSTR-1 workbook matching the GSTN
offline-tool's Excel template (sheets: b2b, cdnr, hsn (b2b), hsn (b2c),
b2cs, docs), for accountants who file through the offline utility instead
of a direct GSP/API upload.

Input is services.gstr1_generator.build_gstr1_excel_rows(items, firm_gstin)'s
flat-rows dict - this file only handles the openpyxl mechanics (headers,
column widths, freeze panes) for each sheet.

Column sets below match the offline tool's long-standing standard layout
for each of these sheets. GSTN revises its template occasionally -
cross-check headers against the current downloaded utility before an
actual filing if a portal upload is ever rejected on column mismatch.
"""
import logging
from typing import List

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Border, Side
    from openpyxl.utils import get_column_letter
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False
    logging.warning("openpyxl not installed. Install it to enable GSTR-1 Excel export.")

logger = logging.getLogger(__name__)

HEADER_FILL = PatternFill("solid", fgColor="1F4E79") if OPENPYXL_AVAILABLE else None
HEADER_FONT = Font(bold=True, color="FFFFFF") if OPENPYXL_AVAILABLE else None
BORDER = Border(*(Side(style="thin"),) * 4) if OPENPYXL_AVAILABLE else None

# (sheet name, [(row key, column label), ...]) - order here is the order
# columns appear in the workbook.
_SHEET_COLUMNS = {
    "b2b": [
        ("gstin", "GSTIN/UIN of Recipient"),
        ("receiver_name", "Receiver Name"),
        ("invoice_number", "Invoice Number"),
        ("invoice_date", "Invoice date"),
        ("invoice_value", "Invoice Value"),
        ("place_of_supply", "Place Of Supply"),
        ("reverse_charge", "Reverse Charge"),
        ("applicable_tax_rate", "Applicable % of Tax Rate"),
        ("invoice_type", "Invoice Type"),
        ("ecommerce_gstin", "E-Commerce GSTIN"),
        ("rate", "Rate"),
        ("taxable_value", "Taxable Value"),
        ("cess", "Cess Amount"),
    ],
    "cdnr": [
        ("gstin", "GSTIN/UIN of Recipient"),
        ("receiver_name", "Receiver Name"),
        ("note_number", "Note Number"),
        ("note_date", "Note Date"),
        ("note_type", "Note Type"),
        ("place_of_supply", "Place Of Supply"),
        ("reverse_charge", "Reverse Charge"),
        ("note_supply_type", "Note Supply Type"),
        ("note_value", "Note Value"),
        ("applicable_tax_rate", "Applicable % of Tax Rate"),
        ("rate", "Rate"),
        ("taxable_value", "Taxable Value"),
        ("cess", "Cess Amount"),
    ],
    "hsn (b2b)": [
        ("hsn", "HSN"),
        ("description", "Description"),
        ("uqc", "UQC"),
        ("total_quantity", "Total Quantity"),
        ("total_value", "Total Value"),
        ("rate", "Rate"),
        ("taxable_value", "Taxable Value"),
        ("integrated_tax", "Integrated Tax Amount"),
        ("central_tax", "Central Tax Amount"),
        ("state_tax", "State/UT Tax Amount"),
        ("cess", "Cess Amount"),
    ],
    "hsn (b2c)": [
        ("hsn", "HSN"),
        ("description", "Description"),
        ("uqc", "UQC"),
        ("total_quantity", "Total Quantity"),
        ("total_value", "Total Value"),
        ("rate", "Rate"),
        ("taxable_value", "Taxable Value"),
        ("integrated_tax", "Integrated Tax Amount"),
        ("central_tax", "Central Tax Amount"),
        ("state_tax", "State/UT Tax Amount"),
        ("cess", "Cess Amount"),
    ],
    "b2cs": [
        ("type", "Type"),
        ("place_of_supply", "Place Of Supply"),
        ("applicable_tax_rate", "Applicable % of Tax Rate"),
        ("rate", "Rate"),
        ("taxable_value", "Taxable Value"),
        ("cess", "Cess Amount"),
        ("ecommerce_gstin", "E-Commerce GSTIN"),
    ],
    "docs": [
        ("nature_of_document", "Nature of Document"),
        ("sr_no_from", "Sr. No. From"),
        ("sr_no_to", "Sr. No. To"),
        ("total_number", "Total Number"),
        ("cancelled", "Cancelled"),
        ("net_issued", "Net Issued"),
    ],
}

# excel_rows dict key (see gstr1_generator.build_gstr1_excel_rows) for each sheet
_SHEET_DATA_KEY = {
    "b2b": "b2b", "cdnr": "cdnr", "hsn (b2b)": "hsn_b2b",
    "hsn (b2c)": "hsn_b2c", "b2cs": "b2cs", "docs": "docs",
}


def _write_sheet(wb, sheet_name: str, rows: List[dict]) -> None:
    columns = _SHEET_COLUMNS[sheet_name]
    ws = wb.create_sheet(sheet_name)

    for col_idx, (_, label) in enumerate(columns, 1):
        cell = ws.cell(row=1, column=col_idx, value=label)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.border = BORDER
    ws.freeze_panes = "A2"
    if columns:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(columns))}1"

    for row_idx, row in enumerate(rows, 2):
        for col_idx, (key, _) in enumerate(columns, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=row.get(key))
            cell.border = BORDER

    for col_idx in range(1, len(columns) + 1):
        ws.column_dimensions[get_column_letter(col_idx)].width = 18


def write_gstr1_excel(excel_rows: dict, path: str) -> None:
    """
    Writes the GSTN-offline-tool-format GSTR-1 workbook to `path`.

    Args:
        excel_rows: services.gstr1_generator.build_gstr1_excel_rows(items, firm_gstin)'s output.
        path: output .xlsx path.
    """
    if not OPENPYXL_AVAILABLE:
        raise RuntimeError("openpyxl not installed")

    wb = Workbook()
    wb.remove(wb.active)  # placeholder default sheet, replaced by the named ones below

    for sheet_name, data_key in _SHEET_DATA_KEY.items():
        _write_sheet(wb, sheet_name, excel_rows.get(data_key, []))

    wb.save(path)
    total_rows = sum(len(excel_rows.get(k, [])) for k in _SHEET_DATA_KEY.values())
    logger.info(f"Wrote GSTR-1 offline-tool workbook to {path} ({total_rows} rows across {len(_SHEET_DATA_KEY)} sheets)")
