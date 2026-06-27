from .invoice_pack import InvoiceValidationPack
from .gst_pack import GSTValidationPack
from .accounting_pack import AccountingValidationPack
from .classification_pack import ClassificationValidationPack
from .mandatory_pack import MandatoryValidationPack

ALL_PACKS = [
    InvoiceValidationPack(),
    GSTValidationPack(),
    AccountingValidationPack(),
    ClassificationValidationPack(),
    MandatoryValidationPack()
]
