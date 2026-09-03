import os

from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.7-flash")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")


if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY was not found in the .env file.")