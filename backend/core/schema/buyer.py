from typing import Optional
from pydantic import Field
from .bundle import VersionedBaseModel
from .confidence import ProvenancedValue

class Buyer(VersionedBaseModel):
    """
    Buyer (Customer) details extracted from the invoice.
    All fields wrap in ProvenancedValue to support field-level confidence and source tracing.
    """
    name: ProvenancedValue[str] = Field(
        default_factory=ProvenancedValue, 
        description="Name of the buyer/customer"
    )
    gstin: ProvenancedValue[str] = Field(
        default_factory=ProvenancedValue, 
        description="GSTIN registration number of the buyer"
    )
    address: ProvenancedValue[str] = Field(
        default_factory=ProvenancedValue, 
        description="Full physical address of the buyer"
    )
    state: ProvenancedValue[str] = Field(
        default_factory=ProvenancedValue, 
        description="Name of the Indian state/union territory of the buyer"
    )
    state_code: ProvenancedValue[str] = Field(
        default_factory=ProvenancedValue, 
        description="Two-digit numerical state code for GST compliance of the buyer"
    )
