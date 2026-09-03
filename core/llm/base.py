from abc import ABC, abstractmethod


# Base interface for all LLM providers
class BaseLLM(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> str:
        pass