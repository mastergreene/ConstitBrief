"""CSRF guard and security headers."""
from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

CSRF_HEADER = "x-constitbrief"


class CsrfMiddleware(BaseHTTPMiddleware):
    """State-changing API calls must carry a custom header.

    Browsers won't send a custom header cross-site without a CORS preflight (which this app
    never grants), so this, plus SameSite=Strict cookies, blocks cross-site request forgery.
    """

    async def dispatch(self, request: Request, call_next):
        if (request.url.path.startswith("/api/") and request.method not in ("GET", "HEAD", "OPTIONS")
                and request.headers.get(CSRF_HEADER) != "1"):
            return JSONResponse({"detail": "Missing request header"}, status_code=403)
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
            "connect-src 'self'; manifest-src 'self'; worker-src 'self'; frame-ancestors 'none'; "
            "form-action 'self'",
        )
        if request.url.path.startswith("/api/"):
            resp.headers.setdefault("Cache-Control", "no-store")
        return resp
