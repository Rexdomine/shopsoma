"""
Authentication endpoints
"""
from datetime import datetime, timedelta
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
    create_magic_link_token,
    verify_magic_link_token,
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
)
from app.api.dependencies import get_current_user, get_current_active_user

router = APIRouter(prefix="/auth", tags=["Authentication"])


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

    # TODO: Send welcome email
    # TODO: Send email verification link

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
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
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
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
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
    )

    db.add(guest_user)
    await db.commit()
    await db.refresh(guest_user)

    return guest_user


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
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }


@router.post("/logout")
async def logout(
    current_user: User = Depends(get_current_active_user)
):
    """
    Logout current user

    Note: Since we're using JWT, actual logout happens client-side by discarding the token.
    This endpoint can be used for logging purposes or token blacklisting in the future.
    """
    # TODO: Implement token blacklist/revocation if needed
    # For now, client-side will discard the token

    return {"message": "Successfully logged out"}
