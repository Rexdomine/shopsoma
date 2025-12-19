from datetime import datetime
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class PreferenceBase(BaseModel):
    interest: Optional[str] = None
    preferred_language: Optional[str] = None
    preferred_currency: Optional[str] = None
    favorite_designers: List[str] = Field(default_factory=list)
    favorite_categories: List[str] = Field(default_factory=list)


class PreferenceResponse(PreferenceBase):
    id: Optional[UUID] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PreferenceUpdate(PreferenceBase):
    pass


class PreferenceDesignerOption(BaseModel):
    id: UUID
    name: str


class PreferenceCategoryOption(BaseModel):
    id: UUID
    name: str
    slug: Optional[str] = None


class PreferenceOptionsResponse(BaseModel):
    designers: List[PreferenceDesignerOption] = Field(default_factory=list)
    categories: List[PreferenceCategoryOption] = Field(default_factory=list)
