from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
from pathlib import Path
from typing import Optional

from agentic_ai_system.orchestration.executor import run_pipeline
from agentic_ai_system.orchestration.executor_stream import stream_sse_pipeline

load_dotenv()
app = FastAPI(title="Agentic AI System (Gemini)", version="2.0.1")

class Query(BaseModel):
    user_prompt: str
    conversation_id: Optional[str] = None

WEB_DIR = Path(__file__).parent / "web"
app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

@app.exception_handler(Exception)
async def all_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"status":"fail","error":{"error_code":"INTERNAL_SERVER_ERROR","message":str(exc),"retryable":False}}
    )

@app.get("/", response_class=HTMLResponse)
def home():
    return (WEB_DIR / "index_steam.html").read_text(encoding="utf-8")

@app.get("/health")
def health():
    return {"ok": True}


@app.post("/query")
def query(q: Query):
    return run_pipeline(q.user_prompt)

@app.post("/query/stream")
def query_stream(q: Query):
    generator = stream_sse_pipeline(
        user_prompt=q.user_prompt,
        conversation_id=q.conversation_id,
    )
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )

@app.get("/index_steam.html", response_class=HTMLResponse)
def index_steam():
    return (WEB_DIR / "index_steam.html").read_text(encoding="utf-8")