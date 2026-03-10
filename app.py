from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from utils import validate_code, compress_code, generate_id
from redis_client import redis_client

import os
import uvicorn

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request}
    )


@app.post("/save")
async def save(code: str = Form(...)):
    validate_code(code)

    # Generate a unique ID — retry if collision
    code_id = generate_id()
    while redis_client.exists(code_id):
        code_id = generate_id()

    # Compress → Base64 encode
    encoded = compress_code(code)

    # Redis is the only storage layer
    redis_client.set(code_id, encoded)

    return {"url": f"/{code_id}"}


@app.get("/{code_id}", response_class=HTMLResponse)
async def get_code_page(request: Request, code_id: str):
    # Lookup encoded data directly from Redis
    encoded = redis_client.get(code_id)
    if not encoded:
        raise HTTPException(404, "Code not found")

    # Return encoded data to frontend — frontend handles decode + decompress
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "encoded": encoded}
    )

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)