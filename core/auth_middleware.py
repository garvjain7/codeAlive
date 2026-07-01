from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from core.redis_client import async_redis

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        user_id = None
        session_id = request.cookies.get("session_id")
        # OPTIMIZATION: Skip session lookup for static assets to reduce TTFB on asset loads.
        is_static = request.url.path.startswith("/static/")
        
        if session_id and not is_static:
            user_id = await async_redis.get(f"session:{session_id}")
                
        request.state.user_id = user_id
        response = await call_next(request)
        
        # Rolling Session: Refresh TTL for 7 days if the user is active.
        # Exclude /auth/logout so we don't accidentally recreate the cookie during logout.
        # Exclude /static/ to avoid sending Set-Cookie headers on every CSS/JS file load.
        if user_id and request.url.path != "/auth/logout" and not request.url.path.startswith("/static/"):
            await async_redis.expire(f"session:{session_id}", 604800)
            response.set_cookie(
                key="session_id",
                value=session_id,
                httponly=True,
                samesite="lax",
                max_age=604800,
                secure=True
            )
            
        return response
