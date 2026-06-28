from typing import Any, Dict, Union, Optional
from backend.core.schema import (
    CanonicalInvoice, Supplier, Buyer, LineItem, TaxSummary, 
    InvoiceMetadata, ProvenancedValue, Classification, FieldConfidence
)
# To avoid relative import issues if run from different entry points, 
# let's write a robust mapper.

def map_gemini_to_canonical(extraction_response: Union[Dict[str, Any], Any]) -> CanonicalInvoice:
    """
    Maps the raw Gemini JSON output (or Pydantic InvoiceExtractionResponse) to the CanonicalInvoice schema.
    """
    # Normalize input to dictionary
    if hasattr(extraction_response, "dict"):
        data = extraction_response.dict()
    elif hasattr(extraction_response, "model_dump"):
        data = extraction_response.model_dump()
    elif isinstance(extraction_response, dict):
        data = extraction_response
    else:
        raise ValueError("Invalid extraction response type")

    sales_items = data.get("sales_items", [])
    purchase_items = data.get("purchase_items", [])
    
    # Identify counterparty info and invoice type
    invoice_type = "Sales"
    first_item = {}
    if sales_items:
        first_item = sales_items[0]
        invoice_type = "Sales"
    elif purchase_items:
        first_item = purchase_items[0]
        invoice_type = "Purchase"

    party_name = first_item.get("party_ledger_name") or data.get("party_ledger_name") or ""
    party_gstin = first_item.get("party_gstin") or data.get("party_gstin") or ""
    place_of_supply = first_item.get("place_of_supply") or data.get("place_of_supply") or ""
    invoice_no = first_item.get("invoice_no") or data.get("invoice_no") or ""
    voucher_date = first_item.get("voucher_date") or data.get("voucher_date") or ""

    # Build Supplier and Buyer
    supplier = Supplier()
    buyer = Buyer()
    
    # Field confidence default for Gemini
    default_confidence = FieldConfidence(
        score=0.9,
        source="Gemini",
        method="LLM Extraction",
        verified=False,
        reason="Extracted from PDF raw text layout"
    )

    if invoice_type == "Sales":
        # Buyer is the counterparty
        buyer.name = ProvenancedValue(value=party_name, confidence=default_confidence)
        buyer.gstin = ProvenancedValue(value=party_gstin, confidence=default_confidence)
        # Supplier is client company (placeholder or extracted if header details parsed)
        supplier.legal_name = ProvenancedValue(value="Client Company", confidence=default_confidence)
    else:
        # Supplier is the counterparty (vendor)
        supplier.legal_name = ProvenancedValue(value=party_name, confidence=default_confidence)
        supplier.gstin = ProvenancedValue(value=party_gstin, confidence=default_confidence)
        # Buyer is client company
        buyer.name = ProvenancedValue(value="Client Company", confidence=default_confidence)

    # Build Invoice Metadata
    metadata = InvoiceMetadata(
        invoice_number=ProvenancedValue(value=invoice_no, confidence=default_confidence),
        invoice_date=ProvenancedValue(value=voucher_date, confidence=default_confidence),
        invoice_type=ProvenancedValue(value=invoice_type, confidence=default_confidence),
        place_of_supply=ProvenancedValue(value=place_of_supply, confidence=default_confidence)
    )

    # Build Line Items
    canonical_items = []
    source_items = sales_items if sales_items else purchase_items
    for s_item in source_items:
        qty = float(s_item.get("qty") or 0.0)
        rate = float(s_item.get("rate") or 0.0)
        discount = float(s_item.get("discount") or 0.0)
        gross = qty * rate
        extracted_taxable = float(s_item.get("taxable_value") or 0.0)

        # Correct taxable_value: GST must be applied on (gross - discount), not gross.
        # If the LLM returned the gross amount when a discount exists, recalculate.
        if discount > 0 and abs(extracted_taxable - gross) < 1.0:
            corrected_taxable = round(gross - discount, 2)
        elif extracted_taxable > 0:
            corrected_taxable = extracted_taxable
        else:
            corrected_taxable = round(max(gross - discount, 0.0), 2)

        item = LineItem(
            description=ProvenancedValue(value=s_item.get("particulars"), confidence=default_confidence),
            hsn_sac=ProvenancedValue(value=s_item.get("hsn"), confidence=default_confidence),
            quantity=ProvenancedValue(value=qty, confidence=default_confidence),
            rate=ProvenancedValue(value=rate, confidence=default_confidence),
            discount=ProvenancedValue(value=discount, confidence=default_confidence),
            advances=ProvenancedValue(value=s_item.get("advances") or 0.0, confidence=default_confidence),
            taxable_value=ProvenancedValue(value=corrected_taxable, confidence=default_confidence),
            cgst_amount=ProvenancedValue(value=s_item.get("cgst_amount") or 0.0, confidence=default_confidence),
            sgst_amount=ProvenancedValue(value=s_item.get("sgst_amount") or 0.0, confidence=default_confidence),
            igst_amount=ProvenancedValue(value=s_item.get("igst_amount") or 0.0, confidence=default_confidence),
            total=ProvenancedValue(value=s_item.get("total_invoice_value") or 0.0, confidence=default_confidence)
        )
        canonical_items.append(item)

    # Build Tax Summary
    tax_summary = TaxSummary(
        taxable_value=ProvenancedValue(value=data.get("overall_taxable_value") or 0.0, confidence=default_confidence),
        cgst_amount=ProvenancedValue(value=data.get("overall_cgst_amount") or 0.0, confidence=default_confidence),
        sgst_amount=ProvenancedValue(value=data.get("overall_sgst_amount") or 0.0, confidence=default_confidence),
        igst_amount=ProvenancedValue(value=data.get("overall_igst_amount") or 0.0, confidence=default_confidence),
        grand_total=ProvenancedValue(value=data.get("overall_total_invoice_value") or 0.0, confidence=default_confidence)
    )

    # Build Classification
    classification = Classification(
        gstr1_category=first_item.get("gstr1_category") or first_item.get("itc_category")
    )

    return CanonicalInvoice(
        supplier=supplier,
        buyer=buyer,
        invoice_metadata=metadata,
        line_items=canonical_items,
        tax_summary=tax_summary,
        classification=classification
    )
