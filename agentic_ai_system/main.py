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
ALLOWED = {
    "openai": {"gpt-4o", "gpt-4o-mini"},
    "openrouter": {"openai/gpt-4o", "openai/gpt-4o-mini", "anthropic/claude-3.5-sonnet"},
    "gemini": {"gemini-1.5-pro", "gemini-1.5-flash"},
}

DEFAULTS = {
    "openai": "gpt-4o-mini",
    "openrouter": "openai/gpt-4o-mini",
    "gemini": "gemini-1.5-flash",
}

class Query(BaseModel):
    user_prompt: str
    conversation_id: Optional[str] = None
    provider: Optional[str] = None   # openai | openrouter | gemini
    model: Optional[str] = None      # เช่น gpt-4o-mini / gemini-1.5-pro / openai/gpt-4o-mini

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
    provider = (q.provider or os.getenv("LLM_PROVIDER", "openai")).lower()
    model = q.model or os.getenv("MODEL") or DEFAULTS.get(provider)

    if provider not in ALLOWED:
        raise HTTPException(status_code=400, detail=f"provider not allowed: {provider}")

    if not model or model not in ALLOWED[provider]:
        raise HTTPException(status_code=400, detail=f"model not allowed for {provider}: {model}")

    generator = stream_sse_pipeline(
        user_prompt=q.user_prompt,
        conversation_id=q.conversation_id,
        provider=provider,
        model=model,
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

@app.get("/diagram", response_class=HTMLResponse)
def diagram():
    md_text = (WEB_DIR / "diagram.md").read_text(encoding="utf-8")

    body_html = markdown.markdown(
        md_text,
        extensions=["fenced_code", "tables"]
    )

    # แปลง code block mermaid → div class="mermaid"
    # NOTE: markdown มักจะ wrap ด้วย <pre><code ...>...</code></pre>
    body_html = body_html.replace(
        '<code class="language-mermaid">',
        '<div class="mermaid">'
    ).replace(
        "</code></pre>",
        "</div>"
    )

    html = f"""
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <link rel="stylesheet" href="{GITHUB_MD_CSS}">
        <script type="module">
          import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';

          mermaid.initialize({{
            startOnLoad: true,
            theme: "base",
            themeVariables: {{
              background: "#0f172a",
              primaryColor: "#1e293b",
              primaryTextColor: "#e2e8f0",
              primaryBorderColor: "#334155",
              lineColor: "#64748b",
              secondaryColor: "#0ea5e9",
              tertiaryColor: "#6366f1",
              fontFamily: "Inter, system-ui, -apple-system, Segoe UI, Roboto, sans-serif",
              fontSize: "16px",
              borderRadius: 12
            }}
          }});
        </script>
        <style>
          body {{
            background: #0f172a;
          }}

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

          /* Mermaid wrapper */
          .mermaid {{
            background: #111827;
            padding: 28px;
            border-radius: 20px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.4);
            overflow-x: auto;
            margin: 18px 0;
          }}

          /* optional: glow เบาๆ */
          .mermaid svg {{
            filter: drop-shadow(0 0 6px rgba(99,102,241,0.35));
          }}
        </style>
        <title>Diagram</title>
      </head>
      <body>
        <article class="markdown-body">
          {body_html}
        </article>
      </body>
    </html>
    """

    return HTMLResponse(content=html)
