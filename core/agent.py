from core.llm.base import BaseLLM


# Main agent that communicates with the selected LLM
class JarvisAgent:
    def __init__(self, llm: BaseLLM):
        self.llm = llm

    def run(self, prompt: str) -> str:
        return self.llm.generate(prompt)