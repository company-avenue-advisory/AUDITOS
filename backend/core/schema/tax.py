from typing import Optional
from pydantic import Field
from .bundle import VersionedBaseModel
from .confidence import ProvenancedValue

class TaxSummary(VersionedBaseModel):
    """
    Summary of values, tax amounts, adjustments and the grand totals for the invoice.
    All properties use ProvenancedValue to trace evaluation confidence.
    """
    taxable_value: ProvenancedValue[float] = Field(
        default_factory=ProvenancedValue, 
        description="Overall base taxable value of the invoice before taxes"
    )
    cgst_amount: ProvenancedValue[float] = Field(
        default_factory=ProvenancedValue, 
        description="Central GST total sum"
    )
    sgst_amount: ProvenancedValue[float] = Field(
        default_factory=ProvenancedValue, 
        description="State GST total sum"
    )
    igst_amount: ProvenancedValue[float] = Field(
        default_factory=ProvenancedValue, 
        description="Integrated GST total sum"
    )
    cess_amount: ProvenancedValue[float] = Field(
        default_factory=ProvenancedValue, 
        description="Cess total sum"
    )
    round_off: ProvenancedValue[float] = Field(
        default_factory=ProvenancedValue, 
        description="Rounding adjustment applied to the final invoice total"
    )
    grand_total: ProvenancedValue[float] = Field(
        default_factory=ProvenancedValue, 
        description="Final total invoice value inclusive of all values, taxes, and roundoff"
    )
