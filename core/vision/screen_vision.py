import base64
import json

from io import BytesIO

from PIL import Image

from core.vision.screen_state import ScreenElement, ScreenState




SCREEN_STATE_PROMPT = """
Analyze the screenshot and return only valid JSON.

Use this format:
{
    "active_app": null,
    "window_title": null,
    "elements": [
        {
            "element_type": "button",
            "label": "Example",
            "x": 0,
            "y": 0,
            "width": 0,
            "height": 0,
            "clickable": true,
            "visible": true
        }
    ]
}

Only include elements that are clearly visible on the screen.
Do not invent hidden or uncertain elements.
Use pixel coordinates relative to the screenshot.
Classify each element by its semantic UI role.
Use "menu" for top menu items, "tab" for tabs, "button" for buttons,
"text_input" for editable text fields, "link" for links, and "icon" for icons.
Do not classify tabs or menu items as buttons when their role is clear.
If you are unsure about a value, use null or 0 when appropriate.
"""

def parse_screen_state(response_text: str) -> ScreenState:
    data = json.loads(response_text)

    elements = []

    for item in data.get("elements", []):

        element = ScreenElement(
            element_type=item.get("element_type", "unknown"),
            label=item.get("label"),
            x=item.get("x", 0),
            y=item.get("y", 0),
            width=item.get("width", 0),
            height=item.get("height", 0),
            clickable=item.get("clickable", False),
            visible=item.get("visible", True),
        )

        elements.append(element)

    return ScreenState(
        active_app=data.get("active_app"),
        window_title=data.get("window_title"),
        elements=elements,
        raw_description=response_text,
    )



class ScreenVision:
    def __init__(self, model):
        self.model = model


    def _image_to_base64(self, image: Image.Image) -> str:
        buffer = BytesIO()

        image.save(
            buffer,
            format="PNG"
        )

        encoded = base64.b64encode(
            buffer.getvalue()
        ).decode("utf-8")

        return encoded


    async def analyze(self, image: Image.Image, goal: str) -> ScreenState:
        encoded_image = self._image_to_base64(image)

        message = {
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": (
                    f"{SCREEN_STATE_PROMPT}\n\n"
                    f"User goal: {goal}"
                ),
            },
            {
                "type": "image",
                "base64": encoded_image,
                "mime_type": "image/png",
            },
        ],
    }

        response = await self.model.ainvoke([message])

        state = parse_screen_state(response.text)

        # Use the real screenshot size
        state.screen_width, state.screen_height = image.size

        return state