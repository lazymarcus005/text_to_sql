from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
from pathlib import Path
from typing import Optional

from agentic_ai_system.orchestration.executor_stream import stream_sse_pipeline
import markdown

GITHUB_MD_CSS = "https://cdnjs.cloudflare.com/ajax/libs/github-markdown-css/5.8.1/github-markdown.min.css"

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

@app.get("/readme", response_class=HTMLResponse)
def readme():
    md_text = (WEB_DIR / "README.md").read_text(encoding="utf-8")
    body_html = markdown.markdown(md_text, extensions=["fenced_code", "tables"])

    html = f"""
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <link rel="stylesheet" href="{GITHUB_MD_CSS}">
        <style>
          /* ให้หน้าตาใกล้ GitHub */
          .markdown-body {{
            box-sizing: border-box;
            min-width: 200px;
            max-width: 980px;
            margin: 0 auto;
            padding: 45px;
          }}
          @media (max-width: 767px) {{
            .markdown-body {{ padding: 15px; }}
          }}
        </style>
        <title>README</title>
      </head>
      <body>
        <article class="markdown-body">
          {body_html}
        </article>
      </body>
    </html>
    """
    return HTMLResponse(content=html)
