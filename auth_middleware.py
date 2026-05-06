from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from redis_client import async_redis

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        user_id = None
        session_id = request.cookies.get("session_id")
        
        if session_id:
            user_id = await async_redis.get(f"session:{session_id}")
                
        request.state.user_id = user_id
        response = await call_next(request)
        return response
