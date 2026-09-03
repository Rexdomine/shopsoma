"""
Authentication schemas
"""
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, validator
from datetime import datetime, date
from uuid import UUID


class UserCreate(BaseModel):
    """User registration schema"""
    email: EmailStr
    password: Optional[str] = Field(None, min_length=8, max_length=100)
    full_name: str = Field(..., min_length=2, max_length=255)
    phone_number: Optional[str] = Field(None, max_length=20)
    date_of_birth: Optional[date] = None
    gender: Optional[str] = Field(None, max_length=50)
    role: str = Field(default="customer", pattern="^(customer|vendor)$")

    @validator("password")
    def password_strength(cls, v, values):
        """Validate password strength"""
        if v is None:
            return v

        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")

        # Check for at least one number
        if not any(char.isdigit() for char in v):
            raise ValueError("Password must contain at least one number")

        # Check for at least one letter
        if not any(char.isalpha() for char in v):
            raise ValueError("Password must contain at least one letter")

        return v

    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@example.com",
                "password": "SecurePass123",
                "full_name": "John Doe",
                "phone_number": "+2348012345678",
                "role": "customer"
            }
        }


class UserLogin(BaseModel):
    """User login schema"""
    email: EmailStr
    password: str

    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@example.com",
                "password": "SecurePass123"
            }
        }


class Token(BaseModel):
    """Token response schema"""
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int


class RefreshTokenRequest(BaseModel):
    """Refresh token request schema"""
    refresh_token: str


class TokenData(BaseModel):
    """Token payload data"""
    user_id: UUID
    email: str
    role: str


class UserResponse(BaseModel):
    """User response schema"""
    id: UUID
    email: str
    full_name: str
    phone_number: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    role: str
    email_verified: bool
    is_active: bool
    profile_image_url: Optional[str] = None
    is_guest_created: bool = False
    created_at: datetime
    last_login_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class MagicLinkRequest(BaseModel):
    """Magic link request schema"""
    email: EmailStr

    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@example.com"
            }
        }


class MagicLinkVerify(BaseModel):
    """Magic link verification schema"""
    token: str

    class Config:
        json_schema_extra = {
            "example": {
                "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
            }
        }


class GuestCheckoutCreate(BaseModel):
    """Guest checkout schema"""
    email: EmailStr
    full_name: str = Field(..., min_length=2, max_length=255)
    phone_number: str = Field(..., max_length=20)

    class Config:
        json_schema_extra = {
            "example": {
                "email": "guest@example.com",
                "full_name": "Guest User",
                "phone_number": "+2348012345678"
            }
        }


class EmailStatusRequest(BaseModel):
    """Request body for checking if an email already has an account."""
    email: EmailStr


class EmailStatusResponse(BaseModel):
    """Response describing account state for an email."""
    email: EmailStr
    exists: bool
    has_password: bool = False
    is_guest_created: bool = False
    is_active: bool = True
    can_claim: bool = False


class UserUpdate(BaseModel):
    """User update schema"""
    email: Optional[EmailStr] = None
    full_name: Optional[str] = Field(None, min_length=2, max_length=255)
    phone_number: Optional[str] = Field(None, max_length=20)

    class Config:
        json_schema_extra = {
            "example": {
                "email": "newemail@example.com",
                "full_name": "John Updated",
                "phone_number": "+2348012345678"
            }
        }


class PasswordReset(BaseModel):
    """Password reset request schema"""
    email: EmailStr

    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@example.com"
            }
        }


class PasswordResetConfirm(BaseModel):
    """Password reset confirmation schema"""
    token: str
    new_password: str = Field(..., min_length=8, max_length=100)

    @validator("new_password")
    def password_strength(cls, v):
        """Validate password strength"""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")

        if not any(char.isdigit() for char in v):
            raise ValueError("Password must contain at least one number")

        if not any(char.isalpha() for char in v):
            raise ValueError("Password must contain at least one letter")

        return v

    class Config:
        json_schema_extra = {
            "example": {
                "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "new_password": "NewSecurePass123"
        }
    }


class ClaimAccountRequest(BaseModel):
    """Claim a silently created guest account"""
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)
    token: str = Field(..., min_length=10, description="Signed claim token from email link")
    full_name: Optional[str] = Field(None, min_length=2, max_length=255)

    @validator("password")
    def password_strength(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if not any(char.isdigit() for char in v):
            raise ValueError("Password must contain at least one number")
        if not any(char.isalpha() for char in v):
            raise ValueError("Password must contain at least one letter")
        return v


class ClaimAccountEmailRequest(BaseModel):
    """Request another account-claim email for a guest user."""
    email: EmailStr
