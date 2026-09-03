from langchain_google_genai import ChatGoogleGenerativeAI

from config.settings import GEMINI_API_KEY, GEMINI_MODEL
from core.tools.calculator import calculator


model = ChatGoogleGenerativeAI(
    model=GEMINI_MODEL,
    google_api_key=GEMINI_API_KEY,
    timeout=20,
    max_retries=0,
)

model_with_tools = model.bind_tools([calculator])

response = model_with_tools.invoke(
    "5 ile 4'ü topla. Calculator tool kullan."
)

print("CONTENT:")
print(response.content)

print("\nTOOL CALLS:")
print(response.tool_calls)