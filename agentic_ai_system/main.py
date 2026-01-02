from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
from pathlib import Path

from agentic_ai_system.orchestration.executor import run_pipeline

load_dotenv()
app = FastAPI(title="Agentic AI System (Gemini)", version="2.0.1")

class Query(BaseModel):
    user_prompt: str

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
    return (WEB_DIR / "index.html").read_text(encoding="utf-8")

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/query")
def query(q: Query):
    return run_pipeline(q.user_prompt)
