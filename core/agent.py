import uuid

from langchain.agents import create_agent
from langchain.agents.middleware import ModelFallbackMiddleware
from langgraph.checkpoint.memory import InMemorySaver

from core.llm.base import BaseLLM
from core.prompts import JARVIS_SYSTEM_PROMPT
from core.tools.calculator import calculator
from core.tools.open_application import open_application
from core.tools.close_application import close_application


# Main Jarvis agent
class JarvisAgent:
    def __init__(self, llm: BaseLLM):
        self.llm = llm

        # Keeps conversation history in memory.
        self.memory = InMemorySaver()

        # Unique ID for this conversation.
        self.thread_id = str(uuid.uuid4())

        # Creates the LangChain agent with tools and fallback model.
        self.agent = create_agent(
            model=self.llm.get_model(),
            tools=[calculator, open_application, close_application],
            system_prompt=JARVIS_SYSTEM_PROMPT,
            middleware=[
                ModelFallbackMiddleware(
                    self.llm.get_fallback_model()
                )
            ],
            checkpointer=self.memory,
        )

    def run(self, prompt: str) -> str:
        # Sends the user message to the agent.
        result = self.agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ]
            },
            config={
                "configurable": {
                    "thread_id": self.thread_id
                }
            },
        )

        # Gets the final Jarvis message.
        content = result["messages"][-1].content

        # Gemini may return the response as text blocks.
        if isinstance(content, list):
            return "".join(
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            )

        return content

    