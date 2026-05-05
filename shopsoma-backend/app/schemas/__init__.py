"""Pydantic schemas"""
from app.schemas.auth import (
    UserCreate,
    UserLogin,
    Token,
    RefreshTokenRequest,
    TokenData,
    UserResponse,
    MagicLinkRequest,
    MagicLinkVerify,
)

__all__ = [
    "UserCreate",
    "UserLogin",
    "Token",
    "RefreshTokenRequest",
    "TokenData",
    "UserResponse",
    "MagicLinkRequest",
    "MagicLinkVerify",
]
