from core.vision.screen_state import ScreenElement, ScreenState
from core.vision.screen_vision import parse_screen_state


def test_screen_element_center():
    element = ScreenElement(
        element_type="button",
        label="Search",
        x=500,
        y=300,
        width=400,
        height=50,
        clickable=True,
    )

    assert element.center == (700, 325)


def test_screen_state():
    element = ScreenElement(
        element_type="text_input",
        label="Google Search",
        x=400,
        y=250,
        width=600,
        height=50,
        clickable=True,
    )

    state = ScreenState(
        active_app="Google Chrome",
        window_title="Google",
        screen_width=1920,
        screen_height=1080,
        elements=[element],
        raw_description="Google search page is open.",
    )

    assert state.active_app == "Google Chrome"
    assert state.window_title == "Google"
    assert state.screen_width == 1920
    assert state.screen_height == 1080

    assert len(state.elements) == 1
    assert state.elements[0].label == "Google Search"
    assert state.elements[0].center == (700, 275)

    assert state.raw_description == "Google search page is open."


def test_screen_state_has_separate_element_lists():
    state1 = ScreenState()
    state2 = ScreenState()

    state1.elements.append(
        ScreenElement(
            element_type="button",
            label="Test Button",
        )
    )

    assert len(state1.elements) == 1
    assert len(state2.elements) == 0


def test_parse_screen_state():
    response_text = """
    {
        "active_app": "Google Chrome",
        "window_title": "Google",
        "elements": [
            {
                "element_type": "button",
                "label": "Search",
                "x": 500,
                "y": 300,
                "width": 200,
                "height": 50,
                "clickable": true,
                "visible": true
            }
        ]
    }
    """

    state = parse_screen_state(response_text)

    assert state.active_app == "Google Chrome"
    assert state.window_title == "Google"
    assert len(state.elements) == 1

    element = state.elements[0]

    assert element.element_type == "button"
    assert element.label == "Search"
    assert element.center == (600, 325)
    assert element.clickable is True
    assert element.visible is True


def test_find_element():
    state = ScreenState(
        elements=[
            ScreenElement(
                element_type="button",
                label="Terminal",
                x=400,
                y=600,
                width=200,
                height=40,
                clickable=True,
            ),
            ScreenElement(
                element_type="button",
                label="Run",
                x=1700,
                y=40,
                width=80,
                height=30,
                clickable=True,
            ),
        ]
    )

    element = state.find_element("terminal")

    assert element is not None
    assert element.label == "Terminal"
    assert element.center == (500, 620)


def test_find_element_with_type():
    state = ScreenState(
        elements=[
            ScreenElement(
                element_type="menu",
                label="Terminal",
                x=300,
                y=10,
                width=50,
                height=20,
                clickable=True,
            ),
            ScreenElement(
                element_type="tab",
                label="Terminal",
                x=450,
                y=200,
                width=100,
                height=40,
                clickable=True,
            ),
        ]
    )

    element = state.find_element(
        "Terminal",
        element_type="tab",
    )

    assert element is not None
    assert element.element_type == "tab"
    assert element.center == (500, 220)



def test_find_element_uses_fallback():
    state = ScreenState(
        elements=[
            ScreenElement(
                element_type="button",
                label="Terminal",
                x=450,
                y=320,
                width=100,
                height=50,
                clickable=True,
            )
        ]
    )

    element = state.find_element(
        "Terminal",
        element_type="tab",
    )

    assert element is not None
    assert element.label == "Terminal"
    assert element.element_type == "button"
    assert element.center == (500, 345)