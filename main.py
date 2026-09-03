from core.llm.gemini import GeminiLLM
from core.agent import JarvisAgent


llm = GeminiLLM()
agent = JarvisAgent(llm)

response = agent.run("Hello")

print(response)