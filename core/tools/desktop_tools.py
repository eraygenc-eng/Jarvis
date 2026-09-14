from langchain_core.tools import tool

from core.tools.desktop_control import (
    get_screen_size,
    get_mouse_position,
    move_mouse,
    click_mouse,
    double_click,
    right_click,
    scroll,
    type_text,
    press_key,
    hotkey
)


@tool
def desktop_get_screen_size() -> dict[str, int]:
    """Return the width and height of the user's current screen."""

    return get_screen_size()


@tool
def desktop_get_mouse_position() -> dict[str, int]:
    """Return the current mouse cursor position."""

    return get_mouse_position()


@tool
def desktop_move_mouse(x: int, y: int, duration: float = 0.3) -> dict:
    """Move the mouse cursor to the given screen coordinates."""

    return move_mouse(
        x=x,
        y=y,
        duration=duration
    )



@tool
def desktop_click_mouse(x: int, y:int, purpose: str, button: str = "left") -> dict:
    """Click the mouse at the given screen coordinates for the stated purpose."""

    return click_mouse(
        x=x,
        y=y,
        button=button
    )



@tool
def desktop_double_click(x: int, y:int, purpose: str, interval: float = 0.15) -> dict:
    """Double-click the left mouse button for the stated purpose."""

    return double_click(
        x=x,
        y=y,
        interval=interval
    )



@tool
def desktop_right_click(x: int, y: int, purpose: str) -> dict:
    """Right-click at the given coordinates for the stated purpose."""

    return right_click(
        x=x,
        y=y
    )




@tool
def desktop_scroll(amount: int) -> dict:
    """Scroll vertically by the given amount."""

    return scroll(amount)




@tool
def desktop_type_text(text: str, purpose: str) -> dict:
    """Type text into the focused field for the stated purpose."""

    return type_text(text)




@tool
def desktop_press_key(key: str, purpose: str, presses: int = 1, interval: float = 0.05) -> dict:
    """Press a keyboard key for the stated purpose."""

    return press_key(
        key=key,
        presses=presses,
        interval=interval
    )



@tool
def desktop_hotkey(keys: list[str], purpose: str) -> dict:
    """Press a keyboard shortcut for the stated purpose."""

    return hotkey(*keys)