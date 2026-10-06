import asyncio
from types import SimpleNamespace

import pytest

from mcp.types import CallToolResult, TextContent

from core.tools.browser import BrowserManager


@pytest.fixture
def browser_manager():
    """
    Create a fresh BrowserManager for every test.

    The real browser session is not started.
    These tests only check internal browser logic.
    """
    return BrowserManager(headless=True)


def test_normal_page_has_no_interruption(browser_manager):
    """
    A normal page should not be detected
    as an interruption.
    """

    page_text = """
    - heading "Flight results"
    - link "Istanbul to Izmir"
    - button "Select flight"
    """

    kind, message = browser_manager._detect_page_interruption(
        page_text
    )

    assert kind is None
    assert message is None
    assert browser_manager._waiting_for_human_verification is False


def test_captcha_is_detected(browser_manager):
    """
    Human verification should be detected
    and browser automation should pause.
    """

    page_text = """
    - heading "Verify you are human"
    - text "Please complete the verification"
    """

    kind, message = browser_manager._detect_page_interruption(
        page_text
    )

    assert kind == "captcha"
    assert message is not None
    assert "Human verification" in message

    # CAPTCHA should pause automatic actions.
    assert browser_manager._waiting_for_human_verification is True


def test_captcha_state_is_cleared_after_verification(
    browser_manager,
):
    """
    CAPTCHA state should be cleared after
    verification disappears from the page.
    """

    captcha_page = """
    - heading "Verify you are human"
    """

    normal_page = """
    - heading "Flight search"
    - textbox "From"
    - textbox "To"
    - button "Search"
    """

    # First page contains CAPTCHA.
    kind, _ = browser_manager._detect_page_interruption(
        captcha_page
    )

    assert kind == "captcha"
    assert browser_manager._waiting_for_human_verification is True

    # The next page no longer contains CAPTCHA.
    kind, message = browser_manager._detect_page_interruption(
        normal_page
    )

    assert kind is None
    assert message is None

    # Browser automation should resume.
    assert browser_manager._waiting_for_human_verification is False


def test_cookie_banner_is_detected(browser_manager):
    """
    A real cookie consent control should
    be detected as a cookie interruption.
    """

    page_text = """
    - dialog "Cookie preferences"
      - button "Accept all cookies"
      - button "Manage preferences"
    """

    kind, message = browser_manager._detect_page_interruption(
        page_text
    )

    assert kind == "cookie"
    assert message is not None
    assert "cookie" in message.lower()

    # Cookie banners should not activate CAPTCHA pause.
    assert browser_manager._waiting_for_human_verification is False


def test_cookie_policy_link_is_not_cookie_interruption(
    browser_manager,
):
    """
    A normal Cookie Policy link should not
    be treated as a blocking cookie banner.
    """

    page_text = """
    - contentinfo
      - link "Cookie Policy"
      - link "Privacy Policy"
      - link "Terms of Service"
    """

    kind, message = browser_manager._detect_page_interruption(
        page_text
    )

    assert kind is None
    assert message is None


def test_popup_is_detected(browser_manager):
    """
    A dialog with popup context and a close button
    should be detected as a popup.
    """

    page_text = """
    - dialog "Newsletter"
      - heading "Subscribe to our newsletter"
      - textbox "Email"
      - button "Close"
    """

    kind, message = browser_manager._detect_page_interruption(
        page_text
    )

    assert kind == "popup"
    assert message is not None
    assert "popup" in message.lower()


def test_captcha_is_cleared_before_cookie_detection(
    browser_manager,
):
    """
    CAPTCHA state must be cleared even when
    a cookie banner appears after verification.
    """

    captcha_page = """
    - heading "Verify you are human"
    """

    cookie_page = """
    - dialog "Cookie preferences"
      - button "Accept all cookies"
    """

    # CAPTCHA appears first.
    kind, _ = browser_manager._detect_page_interruption(
        captcha_page
    )

    assert kind == "captcha"
    assert browser_manager._waiting_for_human_verification is True

    # CAPTCHA disappears and cookie banner appears.
    kind, message = browser_manager._detect_page_interruption(
        cookie_page
    )

    assert kind == "cookie"
    assert message is not None

    # CAPTCHA pause must already be cleared.
    assert browser_manager._waiting_for_human_verification is False


def test_format_observation_contains_captcha_notice(
    browser_manager,
):
    """
    The model-facing observation should contain
    CAPTCHA interruption information.
    """

    page_text = """
    - heading "Verify you are human"
    - text "Please complete the verification"
    """

    observation = browser_manager.observations.capture(
        page_url="https://example.com",
        page_text=page_text,
    )

    formatted = browser_manager._format_observation(
        observation,
        mode="full",
    )

    assert "### Browser Interruption" in formatted
    assert "Type: captcha" in formatted
    assert "Human verification" in formatted

    assert browser_manager._waiting_for_human_verification is True


def test_page_changing_action_is_blocked_during_captcha(
    browser_manager,
):
    """
    Page-changing actions should be blocked
    while human verification is active.
    """

    async def run_test():
        browser_manager._waiting_for_human_verification = True

        request = SimpleNamespace(
            name="browser_click",
            args={
                "ref": "e123",
            },
        )

        handler_called = False

        async def fake_handler(request):
            nonlocal handler_called
            handler_called = True

            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text="CLICKED",
                    )
                ],
                isError=False,
            )

        result = await browser_manager._track_browser_action(
            request,
            fake_handler,
        )

        # The real click must not run.
        assert handler_called is False

        result_text = "\n".join(
            block.text
            for block in result.content
            if block.type == "text"
        )

        assert "BROWSER PAUSED" in result_text
        assert "Human verification" in result_text

    asyncio.run(run_test())


def test_read_only_action_is_allowed_during_captcha(
    browser_manager,
):
    """
    Read-only browser actions should still work.

    Jarvis needs them to check whether
    verification has been completed.
    """

    async def run_test():
        browser_manager._waiting_for_human_verification = True

        request = SimpleNamespace(
            name="browser_snapshot",
            args={},
        )

        handler_called = False

        async def fake_handler(request):
            nonlocal handler_called
            handler_called = True

            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text="SNAPSHOT READ",
                    )
                ],
                isError=False,
            )

        result = await browser_manager._track_browser_action(
            request,
            fake_handler,
        )

        # Snapshot reading should still be allowed.
        assert handler_called is True

        result_text = "\n".join(
            block.text
            for block in result.content
            if block.type == "text"
        )

        assert "SNAPSHOT READ" in result_text

    asyncio.run(run_test())