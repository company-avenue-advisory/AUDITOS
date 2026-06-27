from typing import List, Union, Optional
from backend.core.schema import (
    CanonicalInvoice, Supplier, Buyer, LineItem, TaxSummary, 
    InvoiceMetadata, ProvenancedValue, Classification, FieldConfidence
)
from backend.models import SalesLineItem, PurchaseLineItem

def map_sql_items_to_canonical(db_items: List[Union[SalesLineItem, PurchaseLineItem]]) -> Optional[CanonicalInvoice]:
    """
    Groups a list of SQL line items (from the same invoice task) and transforms them into a single CanonicalInvoice.
    """
    if not db_items:
        return None

    first_item = db_items[0]
    is_sales = isinstance(first_item, SalesLineItem)
    invoice_type = "Sales" if is_sales else "Purchase"

    party_name = first_item.party_ledger_name or ""
    party_gstin = first_item.party_gstin or ""
    place_of_supply = first_item.place_of_supply or ""
    invoice_no = first_item.invoice_no or ""
    voucher_date = first_item.voucher_date or ""

    # Build Supplier and Buyer
    supplier = Supplier()
    buyer = Buyer()
    
    default_confidence = FieldConfidence(
        score=1.0,
        source="Database",
        method="SQL Load",
        verified=True,
        reason="Loaded directly from the verified database records"
    )

    if invoice_type == "Sales":
        buyer.name = ProvenancedValue(value=party_name, confidence=default_confidence)
        buyer.gstin = ProvenancedValue(value=party_gstin, confidence=default_confidence)
        supplier.legal_name = ProvenancedValue(value="Client Company", confidence=default_confidence)
    else:
        supplier.legal_name = ProvenancedValue(value=party_name, confidence=default_confidence)
        supplier.gstin = ProvenancedValue(value=party_gstin, confidence=default_confidence)
        buyer.name = ProvenancedValue(value="Client Company", confidence=default_confidence)

    # Build Invoice Metadata
    metadata = InvoiceMetadata(
        invoice_number=ProvenancedValue(value=invoice_no, confidence=default_confidence),
        invoice_date=ProvenancedValue(value=voucher_date, confidence=default_confidence),
        invoice_type=ProvenancedValue(value=invoice_type, confidence=default_confidence),
        place_of_supply=ProvenancedValue(value=place_of_supply, confidence=default_confidence)
    )

    # Line Items
    canonical_items = []
    overall_taxable = 0.0
    overall_cgst = 0.0
    overall_sgst = 0.0
    overall_igst = 0.0
    overall_total = 0.0

    for db_item in db_items:
        qty = db_item.qty or 0.0
        rate = db_item.rate or 0.0
        taxable_value = db_item.taxable_value or 0.0
        cgst = db_item.cgst_amount or 0.0
        sgst = db_item.sgst_amount or 0.0
        igst = db_item.igst_amount or 0.0
        total = db_item.total_invoice_value or 0.0
        discount = getattr(db_item, 'discount', 0.0) or 0.0

        overall_taxable += taxable_value
        overall_cgst += cgst
        overall_sgst += sgst
        overall_igst += igst
        overall_total += total

        item = LineItem(
            description=ProvenancedValue(value=db_item.particulars, confidence=default_confidence),
            hsn_sac=ProvenancedValue(value=db_item.hsn, confidence=default_confidence),
            quantity=ProvenancedValue(value=qty, confidence=default_confidence),
            rate=ProvenancedValue(value=rate, confidence=default_confidence),
            discount=ProvenancedValue(value=discount, confidence=default_confidence),
            taxable_value=ProvenancedValue(value=taxable_value, confidence=default_confidence),
            cgst_amount=ProvenancedValue(value=cgst, confidence=default_confidence),
            sgst_amount=ProvenancedValue(value=sgst, confidence=default_confidence),
            igst_amount=ProvenancedValue(value=igst, confidence=default_confidence),
            total=ProvenancedValue(value=total, confidence=default_confidence)
        )
        canonical_items.append(item)

    # Build Tax Summary
    tax_summary = TaxSummary(
        taxable_value=ProvenancedValue(value=overall_taxable, confidence=default_confidence),
        cgst_amount=ProvenancedValue(value=overall_cgst, confidence=default_confidence),
        sgst_amount=ProvenancedValue(value=overall_sgst, confidence=default_confidence),
        igst_amount=ProvenancedValue(value=overall_igst, confidence=default_confidence),
        grand_total=ProvenancedValue(value=overall_total, confidence=default_confidence)
    )

    gstr1_category = getattr(first_item, 'gstr1_category', None) or getattr(first_item, 'itc_eligibility', None)
    classification = Classification(gstr1_category=gstr1_category)

    return CanonicalInvoice(
        supplier=supplier,
        buyer=buyer,
        invoice_metadata=metadata,
        line_items=canonical_items,
        tax_summary=tax_summary,
        classification=classification
    )

def map_canonical_to_sales_items(invoice: CanonicalInvoice, task_id: str) -> List[SalesLineItem]:
    """
    Converts a CanonicalInvoice to a list of SQLAlchemy SalesLineItem objects.
    """
    db_items = []
    
    party_ledger_name = invoice.buyer.name.value or ""
    party_gstin = invoice.buyer.gstin.value or ""
    place_of_supply = invoice.invoice_metadata.place_of_supply.value or ""
    invoice_no = invoice.invoice_metadata.invoice_number.value or ""
    voucher_date = invoice.invoice_metadata.invoice_date.value or ""
    gstr1_category = invoice.classification.gstr1_category or ""

    for item in invoice.line_items:
        db_item = SalesLineItem(
            task_id=task_id,
            voucher_date=voucher_date,
            voucher_type="Sales",
            invoice_no=invoice_no,
            party_ledger_name=party_ledger_name,
            party_gstin=party_gstin,
            place_of_supply=place_of_supply,
            particulars=item.description.value or "",
            hsn=item.hsn_sac.value or "",
            qty=item.quantity.value,
            rate=item.rate.value,
            taxable_value=item.taxable_value.value or 0.0,
            discount=item.discount.value or 0.0,
            cgst_amount=item.cgst_amount.value or 0.0,
            sgst_amount=item.sgst_amount.value or 0.0,
            igst_amount=item.igst_amount.value or 0.0,
            total_invoice_value=item.total.value or 0.0,
            gstr1_category=gstr1_category
        )
        db_items.append(db_item)
    return db_items

def map_canonical_to_purchase_items(invoice: CanonicalInvoice, task_id: str) -> List[PurchaseLineItem]:
    """
    Converts a CanonicalInvoice to a list of SQLAlchemy PurchaseLineItem objects.
    """
    db_items = []
    
    party_ledger_name = invoice.supplier.legal_name.value or ""
    party_gstin = invoice.supplier.gstin.value or ""
    place_of_supply = invoice.invoice_metadata.place_of_supply.value or ""
    invoice_no = invoice.invoice_metadata.invoice_number.value or ""
    voucher_date = invoice.invoice_metadata.invoice_date.value or ""
    itc_eligibility = invoice.classification.gstr1_category or ""

    for item in invoice.line_items:
        db_item = PurchaseLineItem(
            task_id=task_id,
            voucher_date=voucher_date,
            voucher_type="Purchase",
            invoice_no=invoice_no,
            party_ledger_name=party_ledger_name,
            party_gstin=party_gstin,
            place_of_supply=place_of_supply,
            particulars=item.description.value or "",
            hsn=item.hsn_sac.value or "",
            qty=item.quantity.value,
            rate=item.rate.value,
            taxable_value=item.taxable_value.value or 0.0,
            cgst_amount=item.cgst_amount.value or 0.0,
            sgst_amount=item.sgst_amount.value or 0.0,
            igst_amount=item.igst_amount.value or 0.0,
            total_invoice_value=item.total.value or 0.0,
            itc_eligibility=itc_eligibility
        )
        db_items.append(db_item)
    return db_items
