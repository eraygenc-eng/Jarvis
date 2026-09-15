import asyncio

from core.llm.factory import create_llm
from core.tools.screen_capture import ScreenCapture
from core.vision.screen_vision import ScreenVision
from core.tools.desktop_control import move_mouse, click_mouse


async def main():
    llm = create_llm()

    capture = ScreenCapture()
    vision = ScreenVision(llm.get_model())

    image = capture.capture_screen()

    state = await vision.analyze(
        image=image,
        goal="Identify the active application and visible clickable UI elements.",
    )

    print("\n--- SCREEN STATE ---")
    print("Active app:", state.active_app)
    print("Window title:", state.window_title)
    print("Screen size:", state.screen_width, "x", state.screen_height)

    print("\n--- ELEMENTS ---")

    for element in state.elements:
        print(
            element.element_type,
            "|",
            element.label,
            "| center:",
            element.center,
            "| clickable:",
            element.clickable,
        )

    target = state.find_element(
        "Terminal",
        element_type="tab",
    )

    if target:
        print("\n--- TARGET ---")
        print("Found:", target.label)
        print("Center:", target.center)

        if target.visible and target.clickable:
            x, y = target.center

            # Move to the detected element
            move_mouse(
                x=x,
                y=y,
                duration=0.5,
            )

            # Click the detected element
            click_mouse(
                x=x,
                y=y,
                button="left",
            )

        else:
            print("Target is not safe to click.")
    else:
        print("\nTarget not found.")


if __name__ == "__main__":
    asyncio.run(main())