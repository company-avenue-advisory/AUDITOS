from typing import Optional
from pydantic import Field
from .bundle import VersionedBaseModel
from .confidence import ProvenancedValue

class LineItem(VersionedBaseModel):
    """
    Represents a single row item in the invoice details, with values wrapped in 
    ProvenancedValue for validation, auditing and UI tracing.
    """
    description: ProvenancedValue[str] = Field(
        default_factory=ProvenancedValue, 
        description="The description of the goods or services"
    )
    hsn_sac: ProvenancedValue[str] = Field(
        default_factory=ProvenancedValue, 
        description="Harmonised System Nomenclature or Service Accounting Code"
    )
    quantity: ProvenancedValue[float] = Field(
        default_factory=ProvenancedValue, 
        description="Number of units of the item"
    )
    unit: ProvenancedValue[str] = Field(
        default_factory=ProvenancedValue, 
        description="Unit of measurement (e.g. PCS, KGS, NOS)"
    )
    rate: ProvenancedValue[float] = Field(
        default_factory=ProvenancedValue, 
        description="Price per single unit"
    )
    discount: ProvenancedValue[float] = Field(
        default_factory=ProvenancedValue, 
        description="Discount amount applicable to the line item"
    )
    taxable_value: ProvenancedValue[float] = Field(
        default_factory=ProvenancedValue, 
        description="Taxable base value after discount, before taxes"
    )
    cgst_amount: ProvenancedValue[float] = Field(
        default_factory=ProvenancedValue, 
        description="Central GST amount"
    )
    sgst_amount: ProvenancedValue[float] = Field(
        default_factory=ProvenancedValue, 
        description="State GST amount"
    )
    igst_amount: ProvenancedValue[float] = Field(
        default_factory=ProvenancedValue, 
        description="Integrated GST amount"
    )
    cess_amount: ProvenancedValue[float] = Field(
        default_factory=ProvenancedValue, 
        description="CESS tax amount"
    )
    advances: ProvenancedValue[float] = Field(
        default_factory=ProvenancedValue, 
        description="Advances amount applicable to the line item"
    )
    total: ProvenancedValue[float] = Field(
        default_factory=ProvenancedValue, 
        description="Total line item value inclusive of all taxes"
    )
