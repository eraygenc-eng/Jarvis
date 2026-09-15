import mss

from dataclasses import dataclass

from PIL import Image



@dataclass
class ScreenInfo:
    monitor: int
    left: int
    top: int
    width: int
    height: int


class ScreenCapture:
    def get_screen_info(self, monitor: int = 1) -> ScreenInfo:
        with mss.mss() as sct:
            screen = sct.monitors[monitor]

            return ScreenInfo(
                monitor=monitor,
                left=screen["left"],
                top=screen["top"],
                width=screen["width"],
                height=screen["height"],
            )


    def capture_screen(self, monitor: int = 1) -> Image.Image:
        with mss.mss() as sct:
            screen = sct.monitors[monitor]
            screenshot = sct.grab(screen)

        image = Image.frombytes(
            "RGB",
            screenshot.size,
            screenshot.rgb
        )

        return image



    def capture_region(self, left: int, top: int, width: int, height: int) -> Image.Image:
        region = {
        "left": left,
        "top": top,
        "width": width,
        "height": height,
        }

        with mss.mss() as sct:
            screenshot = sct.grab(region)

        image = Image.frombytes(
            "RGB",
            screenshot.size,
            screenshot.rgb
        )

        return image



if __name__ == "__main__":
    capture = ScreenCapture()

    info = capture.get_screen_info()

    print("Monitor:", info.monitor)
    print("Left:", info.left)
    print("Top:", info.top)
    print("Width:", info.width)
    print("Height:", info.height)

    image = capture.capture_screen()

    print("Captured image size:", image.size)

    region_image = capture.capture_region(
        left=400,
        top=200,
        width=800,
        height=500,
    )
    print("Region image size:", region_image.size)
