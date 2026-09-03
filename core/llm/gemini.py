from google import genai
from google.genai import errors
from google.genai import types
from core.prompts import JARVIS_SYSTEM_PROMPT

from config.settings import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GEMINI_FALLBACK_MODEL
)
from core.llm.base import BaseLLM


# Gemini implementation of the LLM interface
class GeminiLLM(BaseLLM):
    def __init__(self):
        self.client = genai.Client(api_key=GEMINI_API_KEY)

        self.model = GEMINI_MODEL

        self.chat = self.client.chats.create(
            model=self.model,
            config=types.GenerateContentConfig(
                system_instruction=JARVIS_SYSTEM_PROMPT,
            ),
        )

    def generate(self, prompt: str) -> str:
        history = self.chat.get_history(curated=True)

        try:
            response = self.chat.send_message(prompt)

        except errors.ServerError as error:
            if error.code != 503 or self.model == GEMINI_FALLBACK_MODEL:
                raise

            print(
                f"[LLM] {self.model} is unavailable. "
                f"Switching to {GEMINI_FALLBACK_MODEL}."
            )

            self.model = GEMINI_FALLBACK_MODEL

            self.chat = self.client.chats.create(
                model=self.model,
                history=history,
                config=types.GenerateContentConfig(
                    system_instruction=JARVIS_SYSTEM_PROMPT,
                ),
            )

            response = self.chat.send_message(prompt)


        return response.text