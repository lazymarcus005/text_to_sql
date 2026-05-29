from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
from pathlib import Path
from typing import Optional
import os

from agentic_ai_system.orchestration.executor_stream import stream_sse_pipeline
import markdown

GITHUB_MD_CSS = "https://cdnjs.cloudflare.com/ajax/libs/github-markdown-css/5.8.1/github-markdown.min.css"

load_dotenv()
app = FastAPI(title="Agentic AI System (Gemini)", version="2.0.1")

# price_in / price_out = USD per 1M tokens
MODEL_CATALOG: dict[str, list[dict]] = {
    "openai": [
        {"id": "gpt-4o",       "label": "GPT-4o",        "price_in": 2.50,  "price_out": 10.00},
        {"id": "gpt-4o-mini",  "label": "GPT-4o mini",   "price_in": 0.15,  "price_out": 0.60},
        {"id": "gpt-4.1",      "label": "GPT-4.1",       "price_in": 2.00,  "price_out": 8.00},
        {"id": "gpt-4.1-mini", "label": "GPT-4.1 mini",  "price_in": 0.30,  "price_out": 1.20},
        {"id": "gpt-4.1-nano", "label": "GPT-4.1 nano",  "price_in": 0.10,  "price_out": 0.40},
    ],
    "openrouter": [
        {"id": "openai/gpt-4o",                     "label": "GPT-4o",              "price_in": 2.50,  "price_out": 10.00},
        {"id": "openai/gpt-4o-mini",                "label": "GPT-4o mini",         "price_in": 0.15,  "price_out": 0.60},
        {"id": "openai/gpt-4.1",                    "label": "GPT-4.1",             "price_in": 2.00,  "price_out": 8.00},
        {"id": "openai/gpt-4.1-mini",               "label": "GPT-4.1 mini",        "price_in": 0.30,  "price_out": 1.20},
        {"id": "openai/gpt-4.1-nano",               "label": "GPT-4.1 nano",        "price_in": 0.10,  "price_out": 0.40},
        {"id": "anthropic/claude-opus-4",           "label": "Claude Opus 4",       "price_in": 15.00, "price_out": 75.00},
        {"id": "anthropic/claude-sonnet-4",         "label": "Claude Sonnet 4",     "price_in": 3.00,  "price_out": 15.00},
        {"id": "anthropic/claude-3.5-sonnet",       "label": "Claude 3.5 Sonnet",   "price_in": 3.00,  "price_out": 15.00},
        {"id": "anthropic/claude-3-haiku",          "label": "Claude 3 Haiku",      "price_in": 0.25,  "price_out": 1.25},
        {"id": "google/gemini-2.5-pro",             "label": "Gemini 2.5 Pro",      "price_in": 1.25,  "price_out": 10.00},
        {"id": "google/gemini-2.5-flash",           "label": "Gemini 2.5 Flash",    "price_in": 0.15,  "price_out": 0.60},
        {"id": "deepseek/deepseek-r1",              "label": "DeepSeek R1",         "price_in": 0.55,  "price_out": 2.19},
        {"id": "deepseek/deepseek-chat-v3-0324",    "label": "DeepSeek V3",         "price_in": 0.27,  "price_out": 1.10},
        {"id": "meta-llama/llama-3.3-70b-instruct", "label": "Llama 3.3 70B",      "price_in": 0.12,  "price_out": 0.30},
        {"id": "meta-llama/llama-3.1-8b-instruct",  "label": "Llama 3.1 8B",       "price_in": 0.05,  "price_out": 0.08},
    ],
    "gemini": [
        {"id": "gemini-2.5-pro",       "label": "Gemini 2.5 Pro",        "price_in": 1.25,  "price_out": 10.00},
        {"id": "gemini-2.5-flash",      "label": "Gemini 2.5 Flash",      "price_in": 0.15,  "price_out": 0.60},
        {"id": "gemini-2.5-flash-lite", "label": "Gemini 2.5 Flash Lite", "price_in": 0.10,  "price_out": 0.40},
    ],
}

# ใช้สำหรับ validate
ALLOWED = {
    provider: {m["id"] for m in models}
    for provider, models in MODEL_CATALOG.items()
}

DEFAULTS = {
    "openai": "gpt-4o-mini",
    "openrouter": "openai/gpt-4o-mini",
    "gemini": "gemini-2.5-flash",
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


@app.get("/config/models")
def config_models():
    """Return available providers and their models (with pricing) based on which API keys are set in .env"""
    available: dict[str, list[dict]] = {}

    if os.getenv("OPENAI_API_KEY"):
        available["openai"] = MODEL_CATALOG["openai"]

    if os.getenv("OPENROUTER_API_KEY"):
        available["openrouter"] = MODEL_CATALOG["openrouter"]

    if os.getenv("GOOGLE_API_KEY"):
        available["gemini"] = MODEL_CATALOG["gemini"]

    defaults = {p: DEFAULTS[p] for p in available}

    return JSONResponse({"providers": available, "defaults": defaults})


def _mask(val: str | None, show: int = 6) -> str:
    if not val:
        return "❌ not set"
    return val[:show] + "…" + val[-3:] if len(val) > show + 3 else "✅ set"


@app.get("/config/settings")
def config_settings():
    """Return system config for display (sensitive values are masked)"""
    # API keys status
    api_keys = {
        "OPENAI_API_KEY":    _mask(os.getenv("OPENAI_API_KEY")),
        "OPENROUTER_API_KEY": _mask(os.getenv("OPENROUTER_API_KEY")),
        "GOOGLE_API_KEY":    _mask(os.getenv("GOOGLE_API_KEY")),
    }

    # DB config (mask password)
    db = {
        "DB_HOST":     os.getenv("DB_HOST", "db"),
        "DB_PORT":     os.getenv("DB_PORT", "3306"),
        "DB_NAME":     os.getenv("DB_NAME", "-"),
        "DB_USER":     os.getenv("DB_USER", "-"),
        "DB_PASSWORD": _mask(os.getenv("DB_PASSWORD")),
    }

    # Safety / limits
    safety = {
        "SQL_STATEMENT_TIMEOUT_MS": os.getenv("SQL_STATEMENT_TIMEOUT_MS", "5000"),
        "SQL_MAX_ROWS":             os.getenv("SQL_MAX_ROWS", "200"),
        "TEXT2SQL_MAX_RETRIES":     os.getenv("TEXT2SQL_MAX_RETRIES", "3"),
    }

    # All models catalog (full list, all providers)
    # active providers = those that have an API key set
    active_providers = []
    if os.getenv("OPENAI_API_KEY"):    active_providers.append("openai")
    if os.getenv("OPENROUTER_API_KEY"): active_providers.append("openrouter")
    if os.getenv("GOOGLE_API_KEY"):    active_providers.append("gemini")

    return JSONResponse({
        "api_keys": api_keys,
        "db": db,
        "safety": safety,
        "model_catalog": MODEL_CATALOG,
        "defaults": DEFAULTS,
        "providers": active_providers,
    })


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
