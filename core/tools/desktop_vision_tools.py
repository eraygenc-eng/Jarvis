from langchain_core.tools import tool
from core.tools.screen_capture import ScreenCapture
from core.vision.screen_vision import ScreenVision



def create_desktop_vision_tools(model):
    capture = ScreenCapture()
    vision = ScreenVision(model)


    @tool
    async def desktop_inspect_screen(goal: str, monitor: int = 1) -> dict:
        """Inspect the current screen and return visible UI elements relevant to the goal."""

        # Capture the current screen
        image = capture.capture_screen(
            monitor=monitor
        )

        # Analyze the screen and get the structured screen state
        screen_state = await vision.analyze(
            image=image,
            goal=goal
        )


        # Return simple screen data to the agent
        return {
            "active_app": screen_state.active_app,
            "window_title": screen_state.window_title,
            "elements": [
                {
                    "element_type": element.element_type,
                    "label": element.label,
                    "x": element.x,
                    "y": element.y,
                    "width": element.width,
                    "height": element.height,

                    # Ready-to-use click coordinates
                    "center_x": element.x + element.width // 2,
                    "center_y": element.y + element.height // 2,

                    "clickable": element.clickable,
                    "visible": element.visible,
                }
                for element in screen_state.elements
            ],
        }

    return [
        desktop_inspect_screen,
    ]