import asyncio

from core.llm.factory import create_llm
from core.agent import JarvisAgent
from core.tools.browser import BrowserManager


async def main():
    llm = create_llm()

    # Create and start the browser manager
    browser = BrowserManager()
    await browser.start()

    # Get Playwright browser tools
    browser_tools = browser.get_tools()

    # Create Jarvis with browser tools
    agent = JarvisAgent(llm, browser_tools)

    print("Jarvis is ready. Type 'exit' to quit.")

    try:
        while True:
            prompt = input("You: ")

            if prompt.lower() == "exit":
                print("Jarvis: Goodbye...")
                break

            response = await agent.run(prompt)

            print(f"Jarvis: {response}")

    finally:
        # Close the browser connection
        await browser.stop()

if __name__ == "__main__":
    asyncio.run(main())


# We can't use "await" in def func