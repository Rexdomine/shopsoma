"""
Rate limiting middleware using in-memory storage
Simple implementation without external dependencies
"""
from collections import defaultdict
from datetime import datetime, timedelta
import ipaddress
import time

from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Simple in-memory rate limiting middleware

    Tracks requests per IP address and enforces limits on sensitive endpoints.
    Note: This is a simple implementation suitable for single-instance deployments.
    For production with multiple instances, consider using Redis.
    """

    def __init__(self, app, rate_limit: int = 5, window_seconds: int = 60, trusted_proxy_ips=None):
        super().__init__(app)
        self.rate_limit = rate_limit
        self.window_seconds = window_seconds
        self.requests = defaultdict(list)
        self.last_cleanup = time.time()
        self.trusted_proxy_ips = {
            self._normalize_ip(proxy_ip)
            for proxy_ip in (trusted_proxy_ips or [])
            if self._normalize_ip(proxy_ip)
        }

        # Endpoints to apply rate limiting
        self.protected_endpoints = [
            "/api/v1/auth/login",
            "/api/v1/auth/signup",
            "/api/v1/auth/magic-link/request",
            "/api/v1/auth/password-reset/request",
            "/api/v1/auth/password-reset/confirm",
            "/api/v1/auth/claim-account/request",
            "/api/v1/auth/claim-account",
            "/api/v1/auth/verify-email",
            "/api/v1/users/me/change-password",
        ]

    async def dispatch(self, request: Request, call_next):
        """Process each request"""

        # Only rate limit specific endpoints
        if not any(request.url.path.startswith(endpoint) for endpoint in self.protected_endpoints):
            return await call_next(request)

        # Get client IP
        client_ip = self._get_client_ip(request)

        # Cleanup old entries periodically (every 5 minutes)
        current_time = time.time()
        if current_time - self.last_cleanup > 300:
            self._cleanup_old_requests()
            self.last_cleanup = current_time

        # Get request timestamps for this IP
        request_times = self.requests[client_ip]
        now = datetime.utcnow()

        # Remove requests outside the time window
        cutoff_time = now - timedelta(seconds=self.window_seconds)
        request_times[:] = [t for t in request_times if t > cutoff_time]

        # Check if rate limit is exceeded
        if len(request_times) >= self.rate_limit:
            reset_timestamp = int((now + timedelta(seconds=self.window_seconds)).timestamp())
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": f"Rate limit exceeded. Please try again in {self.window_seconds} seconds."
                },
                headers={
                    "X-RateLimit-Limit": str(self.rate_limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_timestamp),
                    "Retry-After": str(self.window_seconds),
                },
            )

        # Add current request timestamp
        request_times.append(now)

        # Process the request
        response = await call_next(request)

        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(self.rate_limit)
        response.headers["X-RateLimit-Remaining"] = str(self.rate_limit - len(request_times))
        response.headers["X-RateLimit-Reset"] = str(int((now + timedelta(seconds=self.window_seconds)).timestamp()))

        return response

    def _get_client_ip(self, request: Request) -> str:
        immediate_client_ip = self._normalize_ip(request.client.host if request.client else None)
        if not immediate_client_ip:
            return "unknown"

        if immediate_client_ip not in self.trusted_proxy_ips:
            return immediate_client_ip

        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            forwarded_ip = self._extract_forwarded_for_client_ip(forwarded_for)
            if forwarded_ip:
                return forwarded_ip

        real_ip = self._normalize_ip(request.headers.get("x-real-ip"))
        if real_ip:
            return real_ip

        return immediate_client_ip

    @staticmethod
    def _extract_forwarded_for_client_ip(forwarded_for: str) -> str:
        forwarded_chain = [part.strip() for part in forwarded_for.split(",") if part.strip()]
        if not forwarded_chain:
            return ""
        return RateLimitMiddleware._normalize_ip(forwarded_chain[0]) or ""

    @staticmethod
    def _normalize_ip(raw_ip: str) -> str:
        if not raw_ip:
            return ""
        try:
            return ipaddress.ip_address(raw_ip.strip()).compressed
        except ValueError:
            return ""

    def _cleanup_old_requests(self):
        """Clean up old request records to prevent memory bloat"""
        now = datetime.utcnow()
        cutoff_time = now - timedelta(seconds=self.window_seconds * 2)

        # Remove IPs with no recent requests
        ips_to_remove = []
        for ip, times in self.requests.items():
            times[:] = [t for t in times if t > cutoff_time]
            if not times:
                ips_to_remove.append(ip)

        for ip in ips_to_remove:
            del self.requests[ip]


# For more granular control, you can use decorators
class RateLimiter:
    """
    Decorator-based rate limiter for specific endpoints
    """

    def __init__(self, rate_limit: int = 5, window_seconds: int = 60):
        self.rate_limit = rate_limit
        self.window_seconds = window_seconds
        self.requests = defaultdict(list)

    def __call__(self, func):
        async def wrapper(request: Request, *args, **kwargs):
            client_ip = request.client.host if request.client else "unknown"
            request_times = self.requests[client_ip]
            now = datetime.utcnow()

            # Remove old requests
            cutoff_time = now - timedelta(seconds=self.window_seconds)
            request_times[:] = [t for t in request_times if t > cutoff_time]

            # Check rate limit
            if len(request_times) >= self.rate_limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded. Maximum {self.rate_limit} requests per {self.window_seconds} seconds."
                )

            # Add current request
            request_times.append(now)

            # Execute the endpoint
            return await func(request, *args, **kwargs)

        return wrapper


# Commonly used rate limiters
strict_rate_limit = RateLimiter(rate_limit=3, window_seconds=60)  # 3 per minute
auth_rate_limit = RateLimiter(rate_limit=5, window_seconds=60)    # 5 per minute
normal_rate_limit = RateLimiter(rate_limit=20, window_seconds=60) # 20 per minute
