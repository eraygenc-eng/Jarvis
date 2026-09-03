from langchain_google_genai import ChatGoogleGenerativeAI

from config.settings import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GEMINI_FALLBACK_MODEL,
)

from core.llm.base import BaseLLM


# Gemini implementation of the LLM interface
class GeminiLLM(BaseLLM):
    def __init__(self):
        # Primary Gemini model
        self.model = ChatGoogleGenerativeAI(
            model=GEMINI_MODEL,
            google_api_key=GEMINI_API_KEY,
            max_retries=0,
        )

        # Backup model used if the primary model fails
        self.fallback_model = ChatGoogleGenerativeAI(
            model=GEMINI_FALLBACK_MODEL,
            google_api_key=GEMINI_API_KEY,
            max_retries=0,
        )

    # Returns the primary model
    def get_model(self):
        return self.model

    # Returns the fallback model
    def get_fallback_model(self):
        return self.fallback_model