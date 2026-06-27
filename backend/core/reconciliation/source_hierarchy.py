from enum import IntEnum

class SourceRank(IntEnum):
    """
    Ranks sources of truth in order of authority.
    Higher rank means more authority.
    """
    LINE_ITEM_CALCULATION = 100
    INVOICE_TAX_SUMMARY = 95
    INVOICE_HEADER = 80
    LLM_EXTRACTION = 70
    OCR_RAW_CANDIDATE = 50

# Default configurable source of truth mappings for fields
FIELD_SOURCE_AUTHORITY = {
    "taxable_value": SourceRank.LINE_ITEM_CALCULATION,
    "cgst_amount": SourceRank.INVOICE_TAX_SUMMARY,
    "sgst_amount": SourceRank.INVOICE_TAX_SUMMARY,
    "igst_amount": SourceRank.INVOICE_TAX_SUMMARY,
    "cess_amount": SourceRank.INVOICE_TAX_SUMMARY,
    "round_off": SourceRank.INVOICE_TAX_SUMMARY,
    "grand_total": SourceRank.LINE_ITEM_CALCULATION,
    "invoice_number": SourceRank.INVOICE_HEADER,
    "invoice_date": SourceRank.INVOICE_HEADER,
    "gstin": SourceRank.INVOICE_HEADER
}
