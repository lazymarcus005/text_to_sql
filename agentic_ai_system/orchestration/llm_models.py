import os

def get_llm(provider: str | None = None, model: str | None = None, temperature: float | None = None):
    provider = (provider or os.getenv("LLM_PROVIDER", "openai")).lower()
    model = model or os.getenv("MODEL")
    temperature = float(temperature if temperature is not None else os.getenv("TEMPERATURE", "0.0"))

    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model or "gpt-4o-mini",
            temperature=temperature,
            api_key=os.getenv("OPENAI_API_KEY"),
        )

    if provider == "openrouter":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model or "openai/gpt-4o-mini",
            temperature=temperature,
            api_key=os.getenv("OPENROUTER_API_KEY"),
            base_url="https://openrouter.ai/api/v1",
        )

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=model or "gemini-1.5-flash",
            temperature=temperature,
            google_api_key=os.getenv("GOOGLE_API_KEY"),
        )

    raise ValueError(f"Unsupported LLM provider: {provider}")
