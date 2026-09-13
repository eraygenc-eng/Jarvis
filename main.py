import time
import sys
import asyncio

from core.llm.factory import create_llm
from core.agent import JarvisAgent
from core.tools.browser import BrowserManager


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


async def main():
    llm = create_llm()

    # Create and start the browser manager
    browser = BrowserManager()
    await browser.start()

    # Get Playwright browser tools
    browser_tools = browser.get_tools()

    # Create Jarvis with browser tools
    agent = JarvisAgent(
        llm,
        browser_tools,
        observation_store=browser.observations,
    )

    print("Jarvis is ready. Type 'exit' to quit.")

    try:
        while True:
            prompt = input("You: ")

            if prompt.lower() == "exit":
                print("Jarvis: Goodbye...")
                break

            # Start timing the request
            start_time = time.perf_counter()

            response = await agent.run(prompt)

            # Calculate total request time
            elapsed_time = time.perf_counter() - start_time

            print(f"Jarvis: {response}")
            print(f"[Timing] Total: {elapsed_time:.2f} seconds")

    finally:
        # Close the browser connection
        await browser.stop()

if __name__ == "__main__":
    asyncio.run(main())


# We can't use "await" in def func