from core.llm.gemini import GeminiLLM


llm = GeminiLLM()

response = llm.generate("Hello")

print(response)