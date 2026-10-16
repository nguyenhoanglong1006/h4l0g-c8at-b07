"""Ask OptiBot a question from the terminal (same prompt + vector store as the Playground setup).

Usage: python ask.py "How do I add a YouTube video?"
"""

import os
import sys

from openai import OpenAI

from config import load_settings

SYSTEM_PROMPT = """You are OptiBot, the customer-support bot for OptiSigns.com.
• Tone: helpful, factual, concise.
• Only answer using the uploaded docs.
• Max 5 bullet points; else link to the doc.
• Cite up to 3 "Article URL:" lines per reply."""

DEFAULT_MODEL = "gpt-5.4-mini"


def ask(question: str) -> str:
    settings = load_settings()
    if not settings.vector_store_id:
        raise RuntimeError("VECTOR_STORE_ID is not set; run main.py first.")
    response = OpenAI(api_key=settings.openai_api_key).responses.create(
        model=os.getenv("OPENAI_MODEL") or DEFAULT_MODEL,
        instructions=SYSTEM_PROMPT,
        input=question,
        tools=[{"type": "file_search", "vector_store_ids": [settings.vector_store_id]}],
    )
    return response.output_text


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    print(ask(sys.argv[1]))
