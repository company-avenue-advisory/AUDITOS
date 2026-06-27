from typing import Optional, Dict, Any
from pydantic import Field, BaseModel
from .bundle import VersionedBaseModel
from .confidence import ProvenancedValue

class VendorIntel(BaseModel):
    """
    Metadata for recurring supplier learning, layouts, and system intelligence.
    """
    vendor_id: Optional[str] = Field(None, description="Unique ID of verified vendor in Audit OS database")
    vendor_hash: Optional[str] = Field(None, description="Hash of vendor's static profile details")
    layout_id: Optional[str] = Field(None, description="Identified extraction layout template ID for this vendor")
    known_vendor: bool = Field(False, description="True if vendor matches an active database entry")

class Supplier(VersionedBaseModel):
    """
    Supplier details extracted from the invoice, wrapped in ProvenancedValue
    for field-level confidence and traceability.
    """
    legal_name: ProvenancedValue[str] = Field(
        default_factory=ProvenancedValue, 
        description="Legal trading name of the supplier"
    )
    gstin: ProvenancedValue[str] = Field(
        default_factory=ProvenancedValue, 
        description="GSTIN registration number of the supplier"
    )
    pan: ProvenancedValue[str] = Field(
        default_factory=ProvenancedValue, 
        description="PAN (Permanent Account Number) of the supplier"
    )
    address: ProvenancedValue[str] = Field(
        default_factory=ProvenancedValue, 
        description="Full physical address string"
    )
    state: ProvenancedValue[str] = Field(
        default_factory=ProvenancedValue, 
        description="Name of the Indian state/union territory"
    )
    state_code: ProvenancedValue[str] = Field(
        default_factory=ProvenancedValue, 
        description="Two-digit numerical state code for GST compliance"
    )
    pincode: ProvenancedValue[str] = Field(
        default_factory=ProvenancedValue, 
        description="Postal pincode"
    )
    contact_details: ProvenancedValue[str] = Field(
        default_factory=ProvenancedValue, 
        description="Phone, email or other contact info found"
    )
    vendor_intel: VendorIntel = Field(
        default_factory=VendorIntel, 
        description="System vendor intelligence context"
    )
