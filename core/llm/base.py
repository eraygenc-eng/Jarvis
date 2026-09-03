from abc import ABC, abstractmethod
from langchain_core.language_models.chat_models import BaseChatModel


# Base interface for all LLM providers
class BaseLLM(ABC):

    # Returns the primary model.
    @abstractmethod
    def get_model(self) -> BaseChatModel:
        pass

    # Returns the fallback model.
    @abstractmethod
    def get_fallback_model(self) -> BaseChatModel:
        pass