"""
Security utilities for authentication and authorization
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.core.config import settings

# Password hashing context
# Configure bcrypt to truncate long passwords instead of raising error
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__ident="2b"  # Use 2b variant
)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash"""
    # Truncate to 72 bytes for bcrypt
    if len(plain_password.encode('utf-8')) > 72:
        plain_password = plain_password.encode('utf-8')[:72].decode('utf-8', errors='ignore')
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password"""
    # Truncate to 72 bytes for bcrypt
    if len(password.encode('utf-8')) > 72:
        password = password.encode('utf-8')[:72].decode('utf-8', errors='ignore')
    return pwd_context.hash(password)


def get_access_token_expires_delta(role: Optional[str]) -> timedelta:
    if role == "customer":
        customer_days = getattr(settings, "CUSTOMER_ACCESS_TOKEN_EXPIRE_DAYS", None) or 3650
        return timedelta(days=customer_days)
    return timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)


def get_refresh_token_expires_delta(role: Optional[str]) -> timedelta:
    if role == "customer":
        customer_days = getattr(settings, "CUSTOMER_REFRESH_TOKEN_EXPIRE_DAYS", None) or 3650
        return timedelta(days=customer_days)
    return timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Create JWT access token

    Args:
        data: Data to encode in the token (user_id, email, role)
        expires_delta: Optional expiration time delta

    Returns:
        Encoded JWT token
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        role = data.get("role")
        expire = datetime.utcnow() + get_access_token_expires_delta(role)

    to_encode.update({"exp": expire, "iat": datetime.utcnow()})

    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Create JWT refresh token with longer expiration

    Args:
        data: Data to encode in the token

    Returns:
        Encoded JWT refresh token
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        role = data.get("role")
        expire = datetime.utcnow() + get_refresh_token_expires_delta(role)
    to_encode.update({"exp": expire, "iat": datetime.utcnow(), "type": "refresh"})

    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decode and verify JWT token

    Args:
        token: JWT token string

    Returns:
        Decoded token payload or None if invalid
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None


def create_magic_link_token(email: str) -> str:
    """
    Create a magic link token for passwordless authentication

    Args:
        email: User email address

    Returns:
        Encoded JWT token for magic link
    """
    data = {
        "email": email,
        "type": "magic_link",
        "exp": datetime.utcnow() + timedelta(minutes=15)  # Magic links expire in 15 minutes
    }
    return jwt.encode(data, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def verify_magic_link_token(token: str) -> Optional[str]:
    """
    Verify magic link token and extract email

    Args:
        token: Magic link JWT token

    Returns:
        Email address if valid, None otherwise
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])

        if payload.get("type") != "magic_link":
            return None

        email: str = payload.get("email")
        return email
    except JWTError:
        return None


def create_email_verification_token(email: str) -> str:
    """
    Create an email verification token

    Args:
        email: User email address

    Returns:
        Encoded JWT token for email verification
    """
    data = {
        "email": email,
        "type": "email_verification",
        "exp": datetime.utcnow() + timedelta(hours=24)  # Verification links expire in 24 hours
    }
    return jwt.encode(data, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def verify_email_verification_token(token: str) -> Optional[str]:
    """
    Verify email verification token and extract email

    Args:
        token: Email verification JWT token

    Returns:
        Email address if valid, None otherwise
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])

        if payload.get("type") != "email_verification":
            return None

        email: str = payload.get("email")
        return email
    except JWTError:
        return None


def create_account_claim_token(email: str, expires_days: int = 7) -> str:
    """
    Create a token that allows guest users to claim their account.

    Args:
        email: Email address tied to the claim.
        expires_days: Validity window in days.
    """
    data = {
        "email": email,
        "type": "account_claim",
        "exp": datetime.utcnow() + timedelta(days=expires_days)
    }
    return jwt.encode(data, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def verify_account_claim_token(token: str) -> Optional[str]:
    """
    Verify an account claim token and return the encoded email address.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") != "account_claim":
            return None
        return payload.get("email")
    except JWTError:
        return None


def create_password_reset_token(email: str, expires_minutes: int = 60) -> str:
    """
    Create a password reset token for an email address.
    """
    data = {
        "email": email.lower(),
        "type": "password_reset",
        "exp": datetime.utcnow() + timedelta(minutes=expires_minutes),
    }
    return jwt.encode(data, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def verify_password_reset_token(token: str) -> Optional[str]:
    """
    Verify a password reset token and return the encoded email address.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") != "password_reset":
            return None
        return payload.get("email")
    except JWTError:
        return None
