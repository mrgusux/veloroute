from typing import List, Dict, Optional
from pydantic import BaseModel, Field

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    role: str = "admin"

class AddProviderRequest(BaseModel):
    name: str
    api_keys: List[str]
    base_url: Optional[str] = None
    models: Optional[List[str]] = None

class UpdateProviderRequest(BaseModel):
    base_url: Optional[str] = None
    api_keys: Optional[List[str]] = None
    models: Optional[List[str]] = None

class SyncModelsRequest(BaseModel):
    provider: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    filter: Optional[str] = "all"
    save: Optional[bool] = False

class AddKeyRequest(BaseModel):
    keys: List[str]

class SetFallbackRequest(BaseModel):
    fallbacks: Dict[str, List[str]]

class TestCompleteRequest(BaseModel):
    model: str
    prompt: str
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 512
    max_retries: Optional[int] = 2
    retry_delay: Optional[float] = 1.0
    guardrail_mode: Optional[str] = "off"
    injection_protection: Optional[bool] = False
    canary_model: Optional[str] = None
    canary_weight: Optional[float] = None
    shadow_model: Optional[str] = None

class GroupRequest(BaseModel):
    name: str
    models: List[str]

class ProxyRequest(BaseModel):
    proxy: Optional[str] = None

class AliasRequest(BaseModel):
    name: str
    target: str

class VirtualKeyCreateRequest(BaseModel):
    name: str
    budget_usd: Optional[float] = Field(default=None, ge=0)
    budget_alert_threshold: Optional[float] = Field(default=None, ge=0.01, le=1.0)
    budget_alert_webhook: Optional[str] = None
    auto_pause_on_budget: Optional[bool] = True
    rpm_limit: Optional[int] = Field(default=None, gt=0)
    tpm_limit: Optional[int] = Field(default=None, gt=0)
    allowed_models: List[str] = Field(default_factory=list)
    expires_at: Optional[float] = None
    expires_in: Optional[float] = Field(default=None, gt=0)
    metadata: Dict[str, object] = Field(default_factory=dict)

class VirtualKeyUpdateRequest(BaseModel):
    name: Optional[str] = None
    enabled: Optional[bool] = None
    budget_usd: Optional[float] = Field(default=None, ge=0)
    budget_alert_threshold: Optional[float] = Field(default=None, ge=0.01, le=1.0)
    budget_alert_webhook: Optional[str] = None
    auto_pause_on_budget: Optional[bool] = None
    rpm_limit: Optional[int] = Field(default=None, gt=0)
    tpm_limit: Optional[int] = Field(default=None, gt=0)
    allowed_models: Optional[List[str]] = None
    expires_at: Optional[float] = None
    expires_in: Optional[float] = Field(default=None, gt=0)
    metadata: Optional[Dict[str, object]] = None

