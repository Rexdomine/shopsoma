"""Pydantic schemas"""
from app.schemas.auth import (
    UserCreate,
    UserLogin,
    Token,
    TokenData,
    UserResponse,
    MagicLinkRequest,
    MagicLinkVerify,
)

__all__ = [
    "UserCreate",
    "UserLogin",
    "Token",
    "TokenData",
    "UserResponse",
    "MagicLinkRequest",
    "MagicLinkVerify",
]
