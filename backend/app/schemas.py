"""Pydantic request/response schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import AccessLevel, Role, SensitivityLevel


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Role
    username: str


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_.-]+$")
    full_name: str = Field(default="", max_length=120)
    password: str
    role: Role = Role.VIEWER


class UserUpdate(BaseModel):
    role: Role | None = None
    is_active: bool | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: str
    role: Role
    is_active: bool
    created_at: datetime
    locked_until: datetime | None = None
    downloads_blocked_until: datetime | None = None


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    original_name: str
    content_type: str
    size_bytes: int
    sha256: str
    owner_id: int
    owner_username: str = ""
    uploaded_at: datetime
    category: str
    category_confidence: float
    sensitivity: SensitivityLevel
    risk_score: int
    sensitive_findings: dict
    keywords: list
    version_number: int = 1
    manual_classification: bool = False
    key_version: int = 0
    my_access: str = "read"


class DeletedDocumentOut(DocumentOut):
    deleted_at: datetime | None = None
    deleted_by_username: str = ""
    purge_at: datetime | None = None


class VersionOut(BaseModel):
    version_number: int
    original_name: str
    size_bytes: int
    sha256: str
    uploaded_at: datetime
    uploaded_by_username: str = ""
    category: str
    sensitivity: SensitivityLevel
    risk_score: int
    is_current: bool = False


class ClassificationUpdate(BaseModel):
    category: str | None = None
    sensitivity: SensitivityLevel | None = None


class ShareRequest(BaseModel):
    username: str | None = None
    role: Role | None = None
    access_level: AccessLevel = AccessLevel.READ


class PermissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None
    role: Role | None
    access_level: AccessLevel
    granted_at: datetime


class AccessLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
    username: str
    action: str
    document_id: str | None
    success: bool
    ip_address: str
    detail: str


class AnalysisResult(BaseModel):
    category: str
    category_confidence: float
    category_scores: dict[str, float]
    sensitivity: SensitivityLevel
    risk_score: int
    sensitive_findings: dict
    keywords: list[str]


class SearchIntent(BaseModel):
    category: str
    confidence: float


class SearchResultItem(BaseModel):
    document: DocumentOut
    score: float
    reasons: list[str]
    matched_terms: list[str]


class SearchResponse(BaseModel):
    query: str
    total: int
    intent: SearchIntent | None
    results: list[SearchResultItem]


class CountItem(BaseModel):
    label: str
    value: int


class DayActivity(BaseModel):
    date: str
    uploads: int = 0
    events: int = 0
    failed: int = 0


class StatsResponse(BaseModel):
    total_documents: int
    total_bytes: int
    sensitive_documents: int
    average_risk: float
    indexed_documents: int
    by_category: list[CountItem]
    by_sensitivity: list[CountItem]
    top_findings: list[CountItem]
    activity: list[DayActivity]
    failed_logins_7d: int
    active_users_7d: int
    total_users: int | None
    recent_events: list[AccessLogOut]


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
    rule: str
    severity: str
    status: str
    title: str
    description: str
    username: str
    user_id: int | None
    ip_address: str
    document_id: str | None
    score: float
    event_count: int
    response: str
    notes: str
    resolved_at: datetime | None


class AlertUpdate(BaseModel):
    status: str | None = None
    notes: str | None = Field(default=None, max_length=500)
