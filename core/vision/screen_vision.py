import base64

from io import BytesIO

from PIL import Image





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


    async def analyze(self, image: Image.Image, goal: str) -> str:
        encoded_image = self._image_to_base64(image)

        message = {
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": (
                    "Analyze the current computer screen.\n"
                    f"User goal: {goal}\n\n"
                    "Describe what is visible and identify the UI elements "
                    "that are relevant to completing the goal."
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

        return response.text