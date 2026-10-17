import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

HELP_CENTER_URL = "https://support.optisigns.com/api/v2/help_center/en-us/articles.json"
ARTICLES_DIR = Path("data/articles")
LAST_RUN_PATH = Path("output/last_run.json")
STORE_DISPLAY_NAME = "optibot-support-articles"


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str
    store_name: str


def load_settings() -> Settings:
    load_dotenv()
    # API_KEY is accepted because the task's sample command uses `docker run -e API_KEY=...`.
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("API_KEY") or ""
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set (see .env.sample).")
    return Settings(gemini_api_key=api_key, store_name=os.getenv("FILE_SEARCH_STORE", ""))
