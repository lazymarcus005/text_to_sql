FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY agentic_ai_system ./agentic_ai_system
ENV PYTHONPATH=/app

EXPOSE 8000
CMD ["uvicorn", "agentic_ai_system.main:app", "--host", "0.0.0.0", "--port", "8000"]
