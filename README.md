# Agentic AI System (Gemini + LangChain) — production-ish skeleton

Includes:
- Web chat UI at `/` (minimal CSS, clean)
- FastAPI endpoint `POST /query`
- Internal agents (separate files):
  - TextToSQLAgent (Gemini via Google AI Studio) with:
    - structured JSON output
    - output cleaning
    - SQL validation
    - retry loop when LLM output is invalid
  - SQLExecAgent (no LLM) with:
    - read-only style execution (assumes DB perms)
    - statement_timeout
    - row cap (fetchmany)
- Demo Postgres schema + seed data via `db/init.sql`

## Run
```bash
cp .env.example .env
# put your GOOGLE_API_KEY from https://aistudio.google.com/api-keys
docker compose up --build
```

Open:
- Web: http://localhost:8000
- API docs: http://localhost:8000/docs

Test via curl:
```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"user_prompt":"ยอดขายเดือนนี้แยกตามสาขา top 10"}'
```


## pgAdmin
Open http://localhost:5050 (admin@local.dev / admin123)
Register Server: Host=db, Port=5432, Username/Password from .env


## Prompt safety
System prompts are passed through a brace-escape helper to prevent LangChain template variable crashes when including JSON examples.
