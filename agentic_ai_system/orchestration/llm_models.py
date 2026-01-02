import os
from langchain_google_genai import ChatGoogleGenerativeAI

def get_llm():
    # GOOGLE_API_KEY is read automatically from env
    return ChatGoogleGenerativeAI(
        model=os.getenv("GEMINI_MODEL", "gemini-1.5-flash"),
        temperature=float(os.getenv("GEMINI_TEMPERATURE", "0.0")),
    )
