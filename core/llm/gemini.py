from google import genai
from config.settings import GEMINI_API_KEY, GEMINI_MODEL
from core.llm.base import BaseLLM


# Gemini implementation of the LLM interface
class GeminiLLM(BaseLLM):
    def __init__(self):
        self.client = genai.Client(api_key=GEMINI_API_KEY)

        self.chat = self.client.chats.create(
            model=GEMINI_MODEL
        )

    def generate(self, prompt: str) -> str:
        response = self.chat.send_message(prompt)

        return response.text