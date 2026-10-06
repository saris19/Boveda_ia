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
    my_access: str = "read"


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
