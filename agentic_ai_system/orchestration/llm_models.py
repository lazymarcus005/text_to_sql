import os

def get_llm(provider: str | None = None, model: str | None = None, temperature: float | None = None):
    provider = (provider or os.getenv("LLM_PROVIDER", "openai")).lower()
    model = model or os.getenv("MODEL")
    temperature = float(temperature if temperature is not None else os.getenv("TEMPERATURE", "0.0"))

    # Disable internal LLM retries — retry logic is handled at the orchestrator level.
    # This prevents gRPC/HTTP clients from looping indefinitely on auth/credential errors.
    max_retries = 0
    request_timeout = int(os.getenv("LLM_REQUEST_TIMEOUT_SEC", "60"))

    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model or "gpt-4o-mini",
            temperature=temperature,
            api_key=os.getenv("OPENAI_API_KEY"),
            max_retries=max_retries,
            request_timeout=request_timeout,
        )

    if provider == "openrouter":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model or "openai/gpt-4o-mini",
            temperature=temperature,
            api_key=os.getenv("OPENROUTER_API_KEY"),
            base_url="https://openrouter.ai/api/v1",
            max_retries=max_retries,
            request_timeout=request_timeout,
        )

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=model or "gemini-2.5-flash",
            temperature=temperature,
            google_api_key=os.getenv("GOOGLE_API_KEY"),
            max_retries=max_retries,
            timeout=request_timeout,
            # NOTE: Do NOT use transport="rest" — it causes latin-1 encoding errors with Thai text.
            # gRPC retry loop is suppressed by max_retries=0 + short timeout above.
        )

    raise ValueError(f"Unsupported LLM provider: {provider}")
