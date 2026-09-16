import asyncio

from core.llm.factory import create_llm
from core.tools.desktop_vision_tools import create_desktop_vision_tools
from core.tools.desktop_tools import desktop_move_mouse


async def main():
    # Create the configured Jarvis LLM
    llm = create_llm()

    # Create desktop vision tools
    tools = create_desktop_vision_tools(
        llm.get_model()
    )

    # Find the screen inspection tool
    inspect_screen = next(
        tool
        for tool in tools
        if tool.name == "desktop_inspect_screen"
    )

    # Inspect the current screen
    result = await inspect_screen.ainvoke(
        {
            "goal": "Understand the current screen and identify the main visible UI elements.",
            "monitor": 1,
        }
    )

    # Show the detected screen state
    print(result)


        # Find the Run Python File button
    target = next(
        (
            element
            for element in result["elements"]
            if element["label"] == "Run Python File"
        ),
        None
    )

    print("\nTarget:")
    print(target)


    if target is not None:
        # Calculate the center of the detected element
        center_x = target["x"] + target["width"] // 2
        center_y = target["y"] + target["height"] // 2

        print("\nTarget center:")
        print({
            "x": center_x,
            "y": center_y,
        })

        # Move the mouse without clicking
        desktop_move_mouse.invoke(
            {
                "x": center_x,
                "y": center_y,
                "duration": 0.8,
            }
        )


if __name__ == "__main__":
    asyncio.run(main())