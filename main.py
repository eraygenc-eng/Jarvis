from core.llm.factory import create_llm
from core.agent import JarvisAgent


llm = create_llm()
agent = JarvisAgent(llm)

response = agent.run("Hello")

print(response)