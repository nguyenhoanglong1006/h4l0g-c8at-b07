"""OptiBot assistant: system prompt + file_search over the synced Gemini File Search store."""

import os

from google import genai
from google.genai import errors, types

from optibot.config import load_settings

SYSTEM_PROMPT = """You are OptiBot, the customer-support bot for OptiSigns.com.
• Tone: helpful, factual, concise.
• Only answer using the uploaded docs.
• Max 5 bullet points; else link to the doc.
• Cite up to 3 "Article URL:" lines per reply."""

DEFAULT_MODEL = "gemini-3.8-flash"
# Used when the primary model is overloaded (503) even after the SDK's own retries.
FALLBACK_MODEL = "gemini-3.7-flash"
OVERLOADED = 503


def ask(question: str) -> str:
    settings = load_settings()
    if not settings.store_name:
        raise RuntimeError("FILE_SEARCH_STORE is not set; run main.py first.")
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=[types.Tool(file_search=types.FileSearch(file_search_store_names=[settings.store_name]))],
    )
    primary_model = os.getenv("GEMINI_MODEL") or DEFAULT_MODEL
    # Keep a reference for the whole call: an unreferenced Client is closed by __del__ mid-request.
    with genai.Client(api_key=settings.gemini_api_key) as client:
        try:
            response = client.models.generate_content(model=primary_model, contents=question, config=config)
        except errors.ServerError as error:
            if error.code != OVERLOADED or primary_model == FALLBACK_MODEL:
                raise
            response = client.models.generate_content(model=FALLBACK_MODEL, contents=question, config=config)
    return response.text or ""
