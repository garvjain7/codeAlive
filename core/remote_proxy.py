import httpx
import re
from fastapi import Request, Response
from core.config import LIVE_API_URL

# Headers that shouldn't be forwarded directly to/from target
HOP_BY_HOP_HEADERS = {
    "host",
    "content-length",
    "transfer-encoding",
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "upgrade"
}

def _rewrite_set_cookie(cookie_str: str) -> str:
    """
    Rewrite a Set-Cookie header string coming from the deployed server
    so that local browsers on http://localhost:8000 accept and persist it.
    
    - Removes Domain=... attribute
    - Removes Secure attribute for HTTP localhost compatibility
    """
    # Remove Domain attribute (e.g., Domain=codealive.onrender.com; or domain=...)
    cookie_str = re.sub(r'(?i)\bdomain\s*=\s*[^;]+;?\s*', '', cookie_str)
    
    # Remove Secure attribute for HTTP development
    cookie_str = re.sub(r'(?i)\bsecure\s*;?\s*', '', cookie_str)
    
    # Clean up trailing/double semicolons
    cookie_str = re.sub(r';\s*;', ';', cookie_str).strip('; ')
    return cookie_str

async def proxy_request(request: Request, target_path: str = None) -> Response:
    """
    Forward incoming FastAPI Request to LIVE_API_URL and return the rewritten response.
    """
    if target_path is None:
        target_path = request.url.path

    target_path = target_path.lstrip('/')
    target_url = f"{LIVE_API_URL}/{target_path}"
    if request.url.query:
        target_url = f"{target_url}?{request.url.query}"

    # Extract headers to forward
    forward_headers = {}
    for key, value in request.headers.items():
        if key.lower() not in HOP_BY_HOP_HEADERS:
            forward_headers[key] = value

    body = await request.body()

    async with httpx.AsyncClient(follow_redirects=False, timeout=30.0) as client:
        try:
            upstream_resp = await client.request(
                method=request.method,
                url=target_url,
                headers=forward_headers,
                content=body
            )
        except httpx.RequestError as exc:
            return Response(
                content=f'{{"error": "Remote proxy error", "detail": "{str(exc)}"}}',
                status_code=502,
                media_type="application/json"
            )

    # Prepare response headers for client
    response_headers = []
    for key, value in upstream_resp.raw_headers:
        key_str = key.decode("latin-1")
        val_str = value.decode("latin-1")
        
        if key_str.lower() in HOP_BY_HOP_HEADERS:
            continue

        if key_str.lower() == "set-cookie":
            rewritten_cookie = _rewrite_set_cookie(val_str)
            response_headers.append((key_str, rewritten_cookie))
        else:
            response_headers.append((key_str, val_str))

    return Response(
        content=upstream_resp.content,
        status_code=upstream_resp.status_code,
        headers=dict(response_headers),
        media_type=upstream_resp.headers.get("content-type")
    )
