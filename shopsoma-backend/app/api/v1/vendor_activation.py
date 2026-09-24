"""Vendor Activation API endpoints"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import BaseModel, EmailStr
from typing import Optional

from app.core.database import get_db
from app.core.security import create_access_token
from app.models import Vendor, User
from app.services.vendor_otp_service import OTPDeliveryError, VendorOTPService
from app.core.config import settings
from app.services.vendor_activation_service import lock_activation_identity, require_activation_identity


router = APIRouter(prefix="/vendor/activation", tags=["Vendor Activation"])


class InitiateActivationRequest(BaseModel):
    """Request to initiate vendor activation"""
    email: EmailStr


class InitiateActivationResponse(BaseModel):
    """Response after initiating activation"""
    message: str
    masked_email: Optional[str] = None
    token: Optional[str] = None  # Temporary token to identify the vendor during OTP verification
    account_already_setup: bool = False
    reset_password_url: Optional[str] = None
    support_email: Optional[str] = None


class VerifyOTPRequest(BaseModel):
    """Request to verify OTP"""
    token: str
    otp_code: str


class VerifyOTPResponse(BaseModel):
    """Response after OTP verification"""
    message: str
    activation_token: str  # Token to use for password setting
    email: str


class ResendOTPRequest(BaseModel):
    """Request to resend OTP"""
    token: str


class SetPasswordRequest(BaseModel):
    """Request to set vendor password after OTP verification"""
    activation_token: str
    password: str


@router.post("/initiate", response_model=InitiateActivationResponse)
async def initiate_vendor_activation(
    request: InitiateActivationRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Initiate vendor activation by generating and sending OTP code.
    This endpoint is called when a vendor clicks their activation link or manually requests activation.
    """
    # Find user by email
    result = await db.execute(
        select(User).where(User.email == request.email)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor account not found"
        )

    # Check if user is a vendor
    if user.role.value != "vendor":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This account is not a vendor account"
        )

    # Get vendor profile
    vendor_result = await db.execute(
        select(Vendor).where(Vendor.user_id == user.id)
    )
    vendor = vendor_result.scalar_one_or_none()

    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor profile not found"
        )

    row = await lock_activation_identity(db, user_id=user.id)
    if not row:
        raise HTTPException(status_code=404, detail="Vendor profile not found")
    vendor, user = row
    if user.email != request.email:
        raise HTTPException(status_code=401, detail="Invalid activation identity")

    # If this vendor has already completed account setup, provide
    # a user-friendly response with the password reset route.
    if vendor.approved and user.is_active:
        return InitiateActivationResponse(
            message="Your vendor account is already set up. Please reset your password if you cannot sign in, or contact admin for help.",
            account_already_setup=True,
            reset_password_url=f"{settings.FRONTEND_BASE_URL}/forgot-password",
            support_email=settings.ADMIN_EMAIL
        )

    # Check if vendor is approved (required before activation)
    if not vendor.approved:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your vendor account is pending approval. You'll receive an email once approved."
        )

    subject, email = str(user.id), user.email
    vendor, user = await require_activation_identity(db, subject, email)

    # Check if there's already a valid OTP
    existing_otp = await VendorOTPService.get_latest_otp(db, user.email)

    # Only generate new OTP if there's no valid existing one
    if not existing_otp or existing_otp.is_used or existing_otp.is_expired() or existing_otp.is_locked():
        try:
            await VendorOTPService.create_and_send_otp(
                db=db,
                vendor_id=str(vendor.id),
                email=user.email
            )
        except OTPDeliveryError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Unable to send verification code. Please try again."
            )

    # OTP creation commits internally and releases the initial locks.
    vendor, user = await require_activation_identity(db, subject, email)

    # Create a temporary token for this activation session
    # This token is NOT for authentication, just for identifying the vendor during OTP flow
    from datetime import timedelta
    activation_token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "purpose": "vendor_activation"},
        expires_delta=timedelta(minutes=30)  # Short-lived token for activation flow
    )

    return InitiateActivationResponse(
        message="Verification code sent successfully",
        masked_email=VendorOTPService.mask_email(user.email),
        token=activation_token
    )


@router.post("/verify-otp", response_model=VerifyOTPResponse)
async def verify_vendor_otp(
    request: VerifyOTPRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Verify OTP code and activate vendor account.
    Returns authentication tokens upon successful verification.
    """
    # Decode activation token
    from app.core.security import decode_token
    payload = decode_token(request.token)

    if not payload or payload.get("purpose") != "vendor_activation":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired activation link"
        )

    user_id = payload.get("sub")
    email = payload.get("email")

    if not user_id or not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid activation token"
        )

    vendor, user = await require_activation_identity(db, user_id, email)

    # Verify OTP
    success, message, otp = await VendorOTPService.verify_otp(
        db=db,
        email=email,
        plain_code=request.otp_code
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message
        )

    # Verification commits internally. Reacquire and revalidate before any
    # account mutation or password capability; verification never grants approval.
    vendor, user = await require_activation_identity(db, user_id, email)
    if otp.vendor_id != vendor.id:
        raise HTTPException(status_code=401, detail="Invalid activation token")
    user.email_verified = True

    # Mint a distinct capability only after OTP verification. The initiation
    # token must never authorize password persistence by itself.
    from datetime import timedelta
    password_setup_token = create_access_token(
        data={
            "sub": str(user.id),
            "email": user.email,
            "purpose": "vendor_activation_password",
        },
        expires_delta=timedelta(minutes=15),
    )

    await db.commit()

    return VerifyOTPResponse(
        message="Email verified successfully! Please create your password.",
        activation_token=password_setup_token,
        email=user.email
    )


@router.post("/resend-otp")
async def resend_vendor_otp(
    request: ResendOTPRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Resend OTP code to vendor's email.
    """
    # Decode activation token
    from app.core.security import decode_token
    payload = decode_token(request.token)

    if not payload or payload.get("purpose") != "vendor_activation":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired activation link"
        )

    user_id = payload.get("sub")
    email = payload.get("email")

    if not user_id or not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid activation token"
        )

    vendor, user = await require_activation_identity(db, user_id, email)

    # Generate and send new OTP
    try:
        await VendorOTPService.create_and_send_otp(
            db=db,
            vendor_id=str(vendor.id),
            email=user.email
        )
    except OTPDeliveryError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to send verification code. Please try again."
        )

    vendor, user = await require_activation_identity(db, user_id, email)

    return {
        "message": "New verification code sent successfully",
        "masked_email": VendorOTPService.mask_email(user.email)
    }


@router.post("/set-password")
async def set_vendor_password(
    request: SetPasswordRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Set vendor password after OTP verification.
    This completes the activation process and fully activates the account.
    """
    # Decode activation token
    from app.core.security import decode_token, get_password_hash
    payload = decode_token(request.activation_token)

    if not payload or payload.get("purpose") != "vendor_activation_password":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired activation token"
        )

    user_id = payload.get("sub")
    email = payload.get("email")

    if not user_id or not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid activation token"
        )

    # Validate password strength
    if len(request.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long"
        )

    vendor, user = await require_activation_identity(db, user_id, email)
    user_uuid = user.id

    # Claim activation atomically. A conditional update prevents two workers
    # carrying the same capability from both changing the password before
    # either request observes the other's commit.
    password_hash = get_password_hash(request.password)
    activation_result = await db.execute(
        update(User)
        .where(User.id == user_uuid, User.is_active.is_(False))
        .values(
            hashed_password=password_hash,
            is_active=True,
            email_verified=True,
        )
    )
    if activation_result.rowcount != 1:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Vendor account is already active"
        )

    # Generate auth tokens while the eligibility locks still protect identity.
    access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "role": user.role.value}
    )

    from app.core.security import create_refresh_token
    refresh_token = create_refresh_token(
        data={"sub": str(user.id), "email": user.email, "role": user.role.value}
    )

    await db.commit()

    return {
        "message": "Password set successfully! Your account is now active.",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }
