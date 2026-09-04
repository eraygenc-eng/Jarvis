from langchain_openai import ChatOpenAI

from config.settings import (
    OPENAI_API_KEY,
    OPENAI_MODEL
)

from core.llm.base import BaseLLM


# OpenAI implementation of the LLM interface
class OpenAILLM(BaseLLM):
    def __init__(self):
        self.model = ChatOpenAI(
            model=OPENAI_MODEL,
            api_key=OPENAI_API_KEY,
            reasoning_effort="low",
            use_responses_api=True,
        )

    def get_model(self):
        return self.model

    def get_fallback_model(self):
        return self.model