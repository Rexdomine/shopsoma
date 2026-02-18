"""
Authentication endpoints
"""
from datetime import datetime, timedelta
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID

from app.core.database import get_db
from app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    get_access_token_expires_delta,
    create_magic_link_token,
    verify_magic_link_token,
    create_email_verification_token,
    verify_email_verification_token,
    verify_account_claim_token,
    create_password_reset_token,
    verify_password_reset_token,
)
from app.core.config import settings
from app.models.user import User, UserRole
from app.models.vendor import Vendor
from app.schemas.auth import (
    UserCreate,
    UserLogin,
    Token,
    UserResponse,
    MagicLinkRequest,
    MagicLinkVerify,
    GuestCheckoutCreate,
    ClaimAccountRequest,
    EmailStatusRequest,
    EmailStatusResponse,
    ClaimAccountEmailRequest,
    PasswordReset,
    PasswordResetConfirm,
)
from app.api.dependencies import get_current_user, get_current_active_user, get_optional_user
from app.services.email_service import email_service
from app.services.account_claim import queue_account_claim_email

router = APIRouter(prefix="/auth", tags=["Authentication"])
logger = logging.getLogger(__name__)


def _mask_email(email: str) -> str:
    if not email or "@" not in email:
        return email
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        masked_local = f"{local[0]}*"
    else:
        masked_local = f"{local[0]}***{local[-1]}"
    return f"{masked_local}@{domain}"


def _access_expires_in_seconds(role: UserRole) -> int:
    return int(get_access_token_expires_delta(role.value).total_seconds())


@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Register a new user

    - **email**: Valid email address
    - **password**: Strong password (min 8 chars, 1 number, 1 letter)
    - **full_name**: User's full name
    - **phone_number**: Optional phone number
    - **role**: customer or vendor (default: customer)
    """
    # Check if user already exists
    result = await db.execute(select(User).where(User.email == user_data.email))
    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Validate role
    if user_data.role not in ["customer", "vendor"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid role. Must be 'customer' or 'vendor'"
        )

    # Create user
    hashed_password = get_password_hash(user_data.password) if user_data.password else None

    new_user = User(
        email=user_data.email,
        hashed_password=hashed_password,
        full_name=user_data.full_name,
        phone_number=user_data.phone_number,
        date_of_birth=user_data.date_of_birth,
        gender=user_data.gender,
        role=UserRole(user_data.role),
        email_verified=False,  # TODO: Send verification email
        is_active=True,
    )

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    # Create vendor profile if user is a vendor
    if new_user.role == UserRole.VENDOR:
        vendor_profile = Vendor(
            user_id=new_user.id,
            business_name=user_data.full_name,  # Use full_name as business_name initially
            approved=True  # Auto-approve for demo
        )
        db.add(vendor_profile)
        await db.commit()
        await db.refresh(vendor_profile)

    # Send verification email
    try:
        verification_token = create_email_verification_token(new_user.email)
        verification_link = f"{settings.FRONTEND_BASE_URL}/verify-email?token={verification_token}"
        await email_service.send_verification_email(
            email=new_user.email,
            name=new_user.full_name,
            verification_link=verification_link
        )
    except Exception as e:
        # Log error but don't fail registration if email fails
        print(f"Failed to send verification email to {new_user.email}: {e}")

    # Send welcome email
    try:
        await email_service.send_welcome_email(
            email=new_user.email,
            name=new_user.full_name
        )
    except Exception as e:
        # Log error but don't fail registration if email fails
        print(f"Failed to send welcome email to {new_user.email}: {e}")

    return new_user


@router.post("/login", response_model=Token)
async def login(
    login_data: UserLogin,
    db: AsyncSession = Depends(get_db)
):
    """
    Login with email and password

    Returns JWT access token and refresh token
    """
    # Find user by email
    result = await db.execute(select(User).where(User.email == login_data.email))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify password
    if not user.hashed_password or not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if account is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive"
        )

    # Update last login
    user.last_login_at = datetime.utcnow()
    await db.commit()

    # Create tokens
    access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "role": user.role.value}
    )
    refresh_token = create_refresh_token(
        data={"sub": str(user.id), "email": user.email, "role": user.role.value}
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": _access_expires_in_seconds(user.role)
    }


@router.post("/magic-link/request")
async def request_magic_link(
    request_data: MagicLinkRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Request magic link for passwordless authentication

    Sends an email with a magic link that expires in 15 minutes
    """
    # Check if user exists
    result = await db.execute(select(User).where(User.email == request_data.email))
    user = result.scalar_one_or_none()

    # For security, don't reveal if email exists or not
    # Always return success

    if user:
        # Create magic link token
        token = create_magic_link_token(request_data.email)

        # Generate magic link URL
        # In production, this would be your frontend URL
        magic_link = f"http://localhost:5173/auth/magic-link?token={token}"

        # TODO: Send email with magic link
        # background_tasks.add_task(send_magic_link_email, user.email, magic_link)

        print(f"🔗 Magic link for {user.email}: {magic_link}")

    return {
        "message": "If the email exists, a magic link has been sent",
        "expires_in": 900  # 15 minutes
    }


@router.post("/magic-link/verify", response_model=Token)
async def verify_magic_link(
    verify_data: MagicLinkVerify,
    db: AsyncSession = Depends(get_db)
):
    """
    Verify magic link token and authenticate user
    """
    # Verify token and extract email
    email = verify_magic_link_token(verify_data.token)

    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired magic link"
        )

    # Find user
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired magic link"
        )

    # Update last login and verify email
    user.last_login_at = datetime.utcnow()
    user.email_verified = True  # Magic link confirms email
    await db.commit()

    # Create tokens
    access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "role": user.role.value}
    )
    refresh_token = create_refresh_token(
        data={"sub": str(user.id), "email": user.email, "role": user.role.value}
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": _access_expires_in_seconds(user.role)
    }


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_active_user)
):
    """
    Get current authenticated user information
    """
    return current_user


@router.post("/guest-checkout", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def guest_checkout(
    guest_data: GuestCheckoutCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Create a guest user for checkout

    Guest users:
    - Have no password (can't login traditionally)
    - Are created on-the-fly during checkout
    - Can later be converted to full accounts via magic link
    """
    # Check if email already exists
    result = await db.execute(select(User).where(User.email == guest_data.email))
    existing_user = result.scalar_one_or_none()

    if existing_user:
        # If user exists, return them (they can proceed with checkout)
        return existing_user

    # Create guest user (no password)
    guest_user = User(
        email=guest_data.email,
        hashed_password=None,  # No password for guests
        full_name=guest_data.full_name,
        phone_number=guest_data.phone_number,
        role=UserRole.CUSTOMER,
        email_verified=False,
        is_active=True,
        is_guest_created=True,
    )

    db.add(guest_user)
    await db.commit()
    await db.refresh(guest_user)

    return guest_user


@router.post("/email-status", response_model=EmailStatusResponse)
async def check_email_status(
    payload: EmailStatusRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Check whether an email is tied to an existing account.

    Used by checkout to decide whether to prompt for login.
    """
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    if not user:
        return EmailStatusResponse(
            email=payload.email,
            exists=False,
        )

    has_password = bool(user.hashed_password)
    return EmailStatusResponse(
        email=user.email,
        exists=True,
        has_password=has_password,
        is_guest_created=user.is_guest_created,
        is_active=user.is_active,
        can_claim=not has_password
    )


@router.post("/password-reset/request")
async def request_password_reset(
    payload: PasswordReset,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Request a password reset link.

    Always returns success to avoid disclosing whether the email exists.
    """
    masked_email = _mask_email(payload.email)
    logger.info("[Password Reset] Request received for %s", masked_email)
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    if user and user.is_active:
        token = create_password_reset_token(
            user.email,
            settings.PASSWORD_RESET_EXPIRE_MINUTES
        )
        reset_link = f"{settings.FRONTEND_BASE_URL}/reset-password?token={token}"
        if getattr(user, "role", None) == "vendor":
            reset_link = f"{reset_link}&role=vendor"
        logger.info(
            "[Password Reset] Queuing email for user_id=%s email=%s frontend=%s expires_minutes=%s email_enabled=%s api_instance=%s",
            user.id,
            masked_email,
            settings.FRONTEND_BASE_URL,
            settings.PASSWORD_RESET_EXPIRE_MINUTES,
            email_service.enabled,
            "configured" if email_service.api_instance else "None",
        )
        background_tasks.add_task(
            email_service.send_password_reset_email,
            user.email,
            user.full_name,
            reset_link,
            settings.PASSWORD_RESET_EXPIRE_MINUTES
        )
    elif user and not user.is_active:
        logger.info("[Password Reset] Ignored: inactive user_id=%s email=%s", user.id, masked_email)
    else:
        logger.info("[Password Reset] Ignored: no active user for %s", masked_email)

    return {
        "message": "If the email exists, a password reset link has been sent.",
        "expires_in": settings.PASSWORD_RESET_EXPIRE_MINUTES * 60
    }


@router.post("/password-reset/confirm")
async def confirm_password_reset(
    payload: PasswordResetConfirm,
    db: AsyncSession = Depends(get_db)
):
    """
    Confirm password reset with token and new password.
    """
    email = verify_password_reset_token(payload.token)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token"
        )

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token"
        )

    user.hashed_password = get_password_hash(payload.new_password)
    user.is_guest_created = False
    await db.commit()
    await db.refresh(user)

    return {"message": "Password reset successful"}


@router.post("/refresh", response_model=Token)
async def refresh_access_token(
    refresh_token: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Refresh access token using refresh token
    """
    from app.core.security import decode_token

    payload = decode_token(refresh_token)

    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )

    user_id = payload.get("sub")
    email = payload.get("email")
    role = payload.get("role")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )

    # Verify user still exists and is active
    user_uuid = UUID(user_id)
    result = await db.execute(select(User).where(User.id == user_uuid))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )

    # Create new access token
    new_access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "role": user.role.value}
    )

    return {
        "access_token": new_access_token,
        "token_type": "bearer",
        "expires_in": _access_expires_in_seconds(user.role)
    }


@router.post("/logout")
async def logout(
    current_user: Optional[User] = Depends(get_optional_user)
):
    """
    Logout current user

    Works for authenticated users but also returns 200 for guests (no token). Since we
    rely on JWTs, the client is responsible for discarding tokens — this endpoint is a
    best-effort hook for future logging/blacklisting.
    """

    if not current_user:
        # No authenticated user/token, but the client is clearing session locally.
        return {"message": "No active session. Client tokens cleared."}

    return {"message": "Successfully logged out"}


@router.post("/claim-account/request")
async def request_claim_account_email(
    request_data: ClaimAccountEmailRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Send (or resend) a password claim link to a guest-created account.
    """
    result = await db.execute(select(User).where(User.email == request_data.email))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    if user.hashed_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Account already claimed")

    queue_account_claim_email(user, background_tasks)
    return {"message": "Account claim email sent"}


@router.post("/claim-account", response_model=Token)
async def claim_account(
    claim_data: ClaimAccountRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Allow a guest-created account to set a password and become a full account.
    """
    result = await db.execute(select(User).where(User.email == claim_data.email))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    token_email = verify_account_claim_token(claim_data.token)
    if not token_email or token_email.lower() != claim_data.email.lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired claim token"
        )

    if user.hashed_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Account already claimed")

    user.hashed_password = get_password_hash(claim_data.password)
    user.is_guest_created = False
    if claim_data.full_name and not user.full_name:
        user.full_name = claim_data.full_name

    await db.commit()
    await db.refresh(user)

    access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "role": user.role.value}
    )
    refresh_token = create_refresh_token(
        data={"sub": str(user.id), "email": user.email, "role": user.role.value}
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": _access_expires_in_seconds(user.role)
    }


@router.post("/verify-email")
async def verify_email(
    token: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Verify user email address using verification token
    """
    # Verify token and extract email
    email = verify_email_verification_token(token)

    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token"
        )

    # Find user
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if user.email_verified:
        return {"message": "Email already verified"}

    # Mark email as verified
    user.email_verified = True
    await db.commit()

    return {"message": "Email verified successfully"}


@router.post("/resend-verification")
async def resend_verification_email(
    current_user: User = Depends(get_current_active_user)
):
    """
    Resend email verification link to current user
    """
    if current_user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already verified"
        )

    # Send verification email
    try:
        verification_token = create_email_verification_token(current_user.email)
        verification_link = f"{settings.FRONTEND_BASE_URL}/verify-email?token={verification_token}"
        await email_service.send_verification_email(
            email=current_user.email,
            name=current_user.full_name,
            verification_link=verification_link
        )
        return {"message": "Verification email sent successfully"}
    except Exception as e:
        print(f"Failed to send verification email to {current_user.email}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send verification email. Please try again later."
        )
