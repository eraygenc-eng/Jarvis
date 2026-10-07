import asyncio

from types import SimpleNamespace
from unittest.mock import AsyncMock

from core.tools.browser import BrowserManager


def test_detects_later_captcha_patterns():
    manager = BrowserManager()

    page_text = """
    - heading "Security check"
    - text "I'm not a robot"
    """

    kind, message = manager._detect_page_interruption(
        page_text
    )

    assert kind == "captcha"
    assert message is not None
    assert manager._waiting_for_human_verification is True


def test_prefers_reject_all_over_accept_all():
    manager = BrowserManager()

    page_text = """
    - dialog "Cookie preferences"
      - button "Accept all" [ref=e10]
      - button "Reject all" [ref=e11]
    """

    action = manager._find_safe_interruption_action(
        page_text
    )

    assert action == (
        "cookie",
        "Reject all",
        "e11",
    )


def test_uses_accept_all_when_no_safer_cookie_option_exists():
    manager = BrowserManager()

    page_text = """
    - dialog "Cookie preferences"
      - button "Accept all" [ref=e20]
    """

    action = manager._find_safe_interruption_action(
        page_text
    )

    assert action == (
        "cookie",
        "Accept all",
        "e20",
    )


def test_finds_safe_popup_close_button():
    manager = BrowserManager()

    page_text = """
    - dialog "Join our newsletter"
      - heading "Get weekly offers"
      - button "Close" [ref=e30]
    """

    action = manager._find_safe_interruption_action(
        page_text
    )

    assert action == (
        "popup",
        "Close",
        "e30",
    )


def test_never_returns_automatic_action_for_captcha():
    manager = BrowserManager()

    page_text = """
    - heading "Verify you are human"
    - checkbox "I'm not a robot" [ref=e40]
    """

    action = manager._find_safe_interruption_action(
        page_text
    )

    assert action is None
    assert manager._waiting_for_human_verification is True


def test_safe_cookie_action_clicks_expected_ref():
    manager = BrowserManager()

    # Fake the active browser session.
    manager.session = SimpleNamespace()

    manager.session.call_tool = AsyncMock(
        return_value=SimpleNamespace(
            isError=False
        )
    )

    page_text = """
    - dialog "Cookie preferences"
      - button "Accept all" [ref=e50]
      - button "Reject all" [ref=e51]
    """

    handled = asyncio.run(
        manager._handle_safe_interruption(
            page_text
        )
    )

    assert handled is True
    assert manager._page_changed is True

    manager.session.call_tool.assert_awaited_once_with(
        "browser_click",
        arguments={
            "element": "Reject all",
            "target": "e51",
        },
    )


def test_captcha_is_never_clicked():
    manager = BrowserManager()

    # Fake the active browser session.
    manager.session = SimpleNamespace()

    manager.session.call_tool = AsyncMock()

    page_text = """
    - heading "Human verification"
    - text "Verify you are human"
    - button "Continue" [ref=e60]
    """

    handled = asyncio.run(
        manager._handle_safe_interruption(
            page_text
        )
    )

    assert handled is False
    assert manager._waiting_for_human_verification is True

    # CAPTCHA must never trigger an automatic click.
    manager.session.call_tool.assert_not_awaited()


def test_failed_popup_click_does_not_report_success():
    manager = BrowserManager()

    # Simulate a browser click failure.
    manager.session = SimpleNamespace()

    manager.session.call_tool = AsyncMock(
        return_value=SimpleNamespace(
            isError=True
        )
    )

    page_text = """
    - dialog "Subscribe to newsletter"
      - button "Close" [ref=e70]
    """

    handled = asyncio.run(
        manager._handle_safe_interruption(
            page_text
        )
    )

    assert handled is False

    manager.session.call_tool.assert_awaited_once_with(
        "browser_click",
        arguments={
            "element": "Close",
            "target": "e70",
        },
    )


def test_capture_snapshot_handles_cookie_and_reads_page_again():
    manager = BrowserManager()

    # First snapshot contains a cookie banner.
    cookie_snapshot = SimpleNamespace(
        isError=False,
        content=[
            SimpleNamespace(
                type="text",
                text="""
### Page
- Page URL: https://example.com

### Snapshot
```yaml
- dialog "Cookie preferences"
  - button "Accept all" [ref=e10]
  - button "Reject all" [ref=e11]
  """
            )
        ],
    )



def test_capture_snapshot_handles_cookie_then_popup():
    manager = BrowserManager()

    # First snapshot contains a cookie banner.
    cookie_snapshot = SimpleNamespace(
        isError=False,
        content=[
            SimpleNamespace(
                type="text",
                text="""
### Page
- Page URL: https://example.com

### Snapshot
```yaml
- dialog "Cookie preferences"
  - button "Accept all" [ref=e10]
  - button "Reject all" [ref=e11]
  """
            )
        ],
    )




def test_detects_and_handles_generic_cookie_control():
    manager = BrowserManager()

    # Pegasus exposes cookie controls as clickable generic nodes.
    page_text = """
    - generic [ref=e100]:
        İnternet sitesi hizmetlerini sağlayabilmek için
        zorunlu çerezler kullanmaktayız.
    - text: Reddet seçeneğine tıklayarak çerezlerin kullanımını kabul etmeden devam edebilirsiniz.
    - generic [ref=e101] [cursor=pointer]: Çerezler Ayarları
    - generic [ref=e102] [cursor=pointer]: Kabul Et
    """

    kind, message = manager._detect_page_interruption(
        page_text
    )

    assert kind == "cookie"
    assert message is not None

    action = manager._find_safe_interruption_action(
        page_text
    )

    assert action == (
        "cookie",
        "Kabul Et",
        "e102",
    )