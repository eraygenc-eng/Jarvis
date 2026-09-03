from core.llm.factory import create_llm
from core.agent import JarvisAgent


llm = create_llm()
agent = JarvisAgent(llm)

print("Jarvis is ready. Type 'exit' to quit.")

while True:
    prompt = input("You: ")

    if prompt.lower() == "exit":
        print("Jarvis: Goodbye...")
        break

    response = agent.run(prompt)

    print(f"Jarvis: {response}")