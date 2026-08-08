from typing import Any, Optional

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    email: str
    has_llm_config: bool
    sync_token: str


class LLMSettingsRequest(BaseModel):
    api_key: str = Field(min_length=1)
    base_url: Optional[str] = None
    model_id: Optional[str] = None


class LLMSettingsResponse(BaseModel):
    configured: bool
    base_url: Optional[str] = None
    model_id: Optional[str] = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    history: list[dict[str, str]] = Field(default_factory=list)


class ChatResponse(BaseModel):
    final: str
    trace: str
    error: bool = False
    contexts: list[Any] = Field(default_factory=list)


class StatsResponse(BaseModel):
    total_items: int
    memory_conversations: int
    vector_index_count: int
    has_llm_config: bool


class SyncResponse(BaseModel):
    merged_count: int
    total_items: int
    new_items: int
