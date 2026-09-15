import asyncio

from core.llm.factory import create_llm
from core.tools.screen_capture import ScreenCapture
from core.vision.screen_vision import ScreenVision


async def main():
    llm = create_llm()

    capture = ScreenCapture()
    vision = ScreenVision(llm.get_model())

    image = capture.capture_screen()

    result = await vision.analyze(
        image=image,
        goal="Describe the active application and the important visible UI elements.",
    )

    print("\n--- SCREEN VISION RESULT ---")
    print(result)


if __name__ == "__main__":
    asyncio.run(main())