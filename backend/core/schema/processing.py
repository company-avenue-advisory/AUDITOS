from typing import Optional, Any, Dict
from pydantic import Field, BaseModel

class ProcessingContext(BaseModel):
    """
    Context parameters passed through pipeline steps, consolidating arguments
    and resources to ensure a clean execution boundary.
    """
    run_id: str = Field(..., description="Unique run identifier")
    batch_id: str = Field(..., description="Active processing batch job identifier")
    task_id: str = Field(..., description="Active processing task identifier")
    tenant_id: str = Field("default", description="Tenant company identifier")
    firm_id: str = Field("default", description="Auditing firm identifier")
    model: str = Field(..., description="Extraction model to use")
    provider: str = Field(..., description="API provider details")
    temperature: float = Field(0.0, description="Model temperature")
    prompt_version: str = Field("1.0.0", description="Version of the extraction prompt")
    pipeline_version: str = Field("1.0.0", description="Version of the pipeline code")
    feature_flags: Dict[str, Any] = Field(default_factory=dict, description="Enabled pipeline feature flags")
    ocr_engine: Optional[str] = Field(None, description="OCR engine configured (e.g. EasyOCR)")
    storage: Optional[Any] = Field(None, description="Storage provider interface (e.g., GCS connection)")
    logger: Optional[Any] = Field(None, description="Observability logger instance")
    configuration: Dict[str, Any] = Field(default_factory=dict, description="Pipeline operational configuration keys")
