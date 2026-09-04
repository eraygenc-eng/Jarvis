import os

from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

# OpenAI setup
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")

# Gemini settings
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.7-flash")

# For backup
GEMINI_FALLBACK_MODEL = os.getenv(
    "GEMINI_FALLBACK_MODEL",
    "gemini-3.5-flash-lite"
)

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")


if LLM_PROVIDER == "openai" and not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY was not found in the .env file.")

if LLM_PROVIDER == "gemini" and not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY was not found in the .env file.")