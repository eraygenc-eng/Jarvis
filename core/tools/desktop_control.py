import pyautogui
import pyperclip


# Stop PyAutoGUI if the mouse is moved to the top-left corner.
pyautogui.FAILSAFE = True

# Small delay after every PyAutoGUI action.
pyautogui.PAUSE = 0.1



def _validate_coordinates(x: int, y: int):
    """Validate that screen coordinates are inside the current display."""
    width, height = pyautogui.size()

    if not isinstance(x, int) or not isinstance(y, int):
        raise TypeError("x and y must be integers.")

    if x < 0 or x >= width:
        raise ValueError(
            f"x must be between 0 and {width - 1}."
        )

    if y < 0 or y >= height:
        raise ValueError(
            f"y must be between 0 and {height - 1}."
        )




def get_screen_size():
    """Return the current screen width and height."""

    size = pyautogui.size()

    return {
        "width": size.width,
        "height": size.height
    }

def get_mouse_position():
    """Return the current mouse cursor position."""

    position = pyautogui.position()

    return {
        "x": position.x,
        "y": position.y
    }


def move_mouse(x: int, y: int, duration: float = 0.3):
    """Move the mouse cursor to the given screen coordinates."""

    _validate_coordinates(x, y)

    if duration < 0 or duration > 5:
        raise ValueError("duration must be between 0 and 5 seconds.")

    pyautogui.moveTo(
        x=x,
        y=y,
        duration=duration
    )

    return {
        "success": True,
        "x": x,
        "y": y
    }


def click_mouse(x: int, y:int, button: str = "left"):
    """Click the mouse at the given screen coordinates."""

    _validate_coordinates(x, y)

    pyautogui.click(
        x=x,
        y=y,
        button=button
    )

    return {
        "success": True,
        "x": x,
        "y": y,
        "button": button,
    }


def double_click(x: int, y:int, interval: float = 0.15):
    """Double-click the left mouse button at the given coordinates."""

    pyautogui.doubleClick(
        x=x,
        y=y,
        interval=interval,
        button="left"
    )

    return {
        "success": True,
        "x": x,
        "y": y,
    }


def right_click(x:int, y: int):
    """Right-click at the given screen coordinates."""

    pyautogui.rightClick(
        x=x,
        y=y
    )

    return {
        "success": True,
        "x": x,
        "y": y,
    }


def scroll(amount: int):
    """Scroll vertically by the given amount."""

    if amount < -100 or amount > 100:
        raise ValueError("amount must be between -100 and 100.")
    
    pyautogui.scroll(amount)

    return {
        "success": True,
        "amount": amount,
    }


def type_text(text: str):
    """Type text into the currently focused input field."""

    pyperclip.copy(text)
    pyautogui.hotkey("ctrl", "v")

    return {
        "success": True,
        "text": text,
    }


def press_key(key: str, presses: int = 1, interval: float = 0.05):
    """Press a keyboard key one or more times."""

    key = key.lower().strip()

    if key not in pyautogui.KEYBOARD_KEYS:
        raise ValueError(f"Unsupported key: {key}")

    if presses < 1 or presses > 20:
        raise ValueError("presses must be between 1 and 20.")

    pyautogui.press(
        key,
        presses=presses,
        interval=interval
    )


    return {
        "success": True,
        "key": key,
        "presses": presses,
    }


def hotkey(*keys: str):
    """Press a keyboard shortcut."""

    normalized_keys = [
        key.lower().strip()
        for key in keys
    ]

    if len(normalized_keys) < 2:
        raise ValueError("A hotkey must contain at least two keys.")

    for key in normalized_keys:
        if key not in pyautogui.KEYBOARD_KEYS:
            raise ValueError(f"Unsupported key: {key}")

    pyautogui.hotkey(*normalized_keys)

    return {
        "success": True,
        "keys": normalized_keys,
    }