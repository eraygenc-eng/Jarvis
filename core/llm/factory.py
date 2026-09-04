from config.settings import LLM_PROVIDER

from core.llm.gemini import GeminiLLM
from core.llm.openai import OpenAILLM


# Creates the selected LLM provider
def create_llm():
    if LLM_PROVIDER == "openai":
        return OpenAILLM()

    if LLM_PROVIDER == "gemini":
        return GeminiLLM()

    raise ValueError(f"Unsupported LLM provider: {LLM_PROVIDER}")