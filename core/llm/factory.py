from config.settings import LLM_PROVIDER
from core.llm.gemini import GeminiLLM


# Creates the selected LLM provider
def create_llm():
    if LLM_PROVIDER == "gemini":
        return GeminiLLM()

    raise ValueError(f"Unsupported LLM provider: {LLM_PROVIDER}")