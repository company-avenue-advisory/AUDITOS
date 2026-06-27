from typing import Optional, List
from pydantic import Field, BaseModel
from .bundle import VersionedBaseModel
from .confidence import ProvenancedValue
from .supplier import Supplier
from .buyer import Buyer
from .items import LineItem
from .tax import TaxSummary

class EInvoiceDetails(BaseModel):
    """
    Electronic invoice registration details.
    """
    irn: Optional[str] = Field(None, description="Invoice Reference Number")
    ack_no: Optional[str] = Field(None, description="Acknowledgement Number")
    ack_date: Optional[str] = Field(None, description="Acknowledgement Date")

class EWayBillDetails(BaseModel):
    """
    Electronic waybill registration details.
    """
    eway_bill_no: Optional[str] = Field(None, description="E-Way Bill Number")
    eway_bill_date: Optional[str] = Field(None, description="E-Way Bill Date")

class InvoiceMetadata(VersionedBaseModel):
    """
    Transactional metadata of the invoice.
    """
    invoice_number: ProvenancedValue[str] = Field(
        default_factory=ProvenancedValue, 
        description="Unique invoice sequence number"
    )
    invoice_date: ProvenancedValue[str] = Field(
        default_factory=ProvenancedValue, 
        description="Date the invoice was issued (DD-MM-YYYY or DD-MMM-YYYY)"
    )
    due_date: ProvenancedValue[str] = Field(
        default_factory=ProvenancedValue, 
        description="Due date for payment"
    )
    invoice_type: ProvenancedValue[str] = Field(
        default_factory=ProvenancedValue, 
        description="Document type (e.g. Sales, Purchase, Credit Note, Debit Note)"
    )
    currency: ProvenancedValue[str] = Field(
        default_factory=ProvenancedValue, 
        description="Three-letter currency code (e.g., INR, USD)"
    )
    financial_year: ProvenancedValue[str] = Field(
        default_factory=ProvenancedValue, 
        description="Financial year associated with the transaction (e.g., 2026-27)"
    )
    reverse_charge: ProvenancedValue[bool] = Field(
        default_factory=ProvenancedValue, 
        description="True if reverse charge applies to this invoice transaction"
    )
    place_of_supply: ProvenancedValue[str] = Field(
        default_factory=ProvenancedValue, 
        description="Indian state name or code representing the place of supply"
    )
    e_invoice_details: Optional[EInvoiceDetails] = Field(None, description="E-Invoice registry details if applicable")
    e_way_bill_details: Optional[EWayBillDetails] = Field(None, description="E-Way Bill registry details if applicable")

class PaymentInformation(BaseModel):
    """
    Information regarding payment details, bank accounts, terms and methods.
    """
    bank_name: Optional[str] = Field(None, description="Bank Name")
    account_number: Optional[str] = Field(None, description="Bank Account Number")
    ifsc_code: Optional[str] = Field(None, description="IFSC / Branch Routing Code")
    payment_terms: Optional[str] = Field(None, description="Payment Terms / Credit Days")
    payment_method: Optional[str] = Field(None, description="Payment Method (e.g. NEFT, Bank Transfer)")

class TransportInformation(BaseModel):
    """
    Information regarding delivery and transporter details.
    """
    transporter_name: Optional[str] = Field(None, description="Name of Transporter / Logistics Vendor")
    vehicle_number: Optional[str] = Field(None, description="Vehicle Registration Number")
    lr_number: Optional[str] = Field(None, description="Lorry Receipt Number")
    lr_date: Optional[str] = Field(None, description="Lorry Receipt Date")

class Classification(BaseModel):
    """
    Classification labels reserved for audit, accounting, and GSTR reporting rules.
    """
    gstr1_category: Optional[str] = Field(None, description="GSTR-1 category (B2B, B2C, CDNUR, etc.)")
    document_type: Optional[str] = Field(None, description="Document categorization for ERP routing")
    transaction_type: Optional[str] = Field(None, description="e.g., Intra-State, Inter-State")
    supply_type: Optional[str] = Field(None, description="Taxability type (Taxable, Exempt, Nil-Rated)")

class CanonicalInvoice(VersionedBaseModel):
    """
    The Canonical Invoice Model, defining a structured business invoice
    independent of any specific ERP schema, LLM output, or database representation.
    """
    supplier: Supplier = Field(default_factory=Supplier, description="Supplier party details")
    buyer: Buyer = Field(default_factory=Buyer, description="Buyer party details")
    invoice_metadata: InvoiceMetadata = Field(default_factory=InvoiceMetadata, description="Invoice sequence and date headers")
    line_items: List[LineItem] = Field(default_factory=list, description="Extracted line item rows")
    tax_summary: TaxSummary = Field(default_factory=TaxSummary, description="Summarized tax calculations and grand totals")
    payment_info: Optional[PaymentInformation] = Field(None, description="Extracted payment details")
    transport_info: Optional[TransportInformation] = Field(None, description="Extracted transport details")
    classification: Classification = Field(default_factory=Classification, description="Reserved compliance/GSTR classification fields")
