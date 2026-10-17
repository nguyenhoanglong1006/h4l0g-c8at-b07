"""OptiBot assistant: system prompt + file_search over the synced Gemini File Search store."""

import os

from google import genai
from google.genai import types

from optibot.config import load_settings

SYSTEM_PROMPT = """You are OptiBot, the customer-support bot for OptiSigns.com.
• Tone: helpful, factual, concise.
• Only answer using the uploaded docs.
• Max 5 bullet points; else link to the doc.
• Cite up to 3 "Article URL:" lines per reply."""

DEFAULT_MODEL = "gemini-3.8-flash"


def ask(question: str) -> str:
    settings = load_settings()
    if not settings.store_name:
        raise RuntimeError("FILE_SEARCH_STORE is not set; run main.py first.")
    # Keep a reference for the whole call: an unreferenced Client is closed by __del__ mid-request.
    with genai.Client(api_key=settings.gemini_api_key) as client:
        response = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL") or DEFAULT_MODEL,
            contents=question,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                tools=[
                    types.Tool(file_search=types.FileSearch(file_search_store_names=[settings.store_name]))
                ],
            ),
        )
    return response.text or ""
