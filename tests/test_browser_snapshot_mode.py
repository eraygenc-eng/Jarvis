import asyncio

from datetime import datetime, timezone
from types import SimpleNamespace

from mcp.types import CallToolResult, TextContent

from core.tools.browser import BrowserManager


def make_observation(page_text: str):
    return SimpleNamespace(
        observation_id="test-observation",
        page_url="https://www.hepsiburada.com/ara?q=airpods",
        page_text=page_text,
        captured_at=datetime.now(timezone.utc),
        kind="page",
    )


def make_manager():
    # _format_observation does not need a running browser session.
    return BrowserManager.__new__(BrowserManager)


def test_focus_miss_never_falls_back_to_full_snapshot():
    manager = make_manager()

    observation = make_observation(
        """
- region "AirPods sonuçları" [ref=e1]
  - link "Apple AirPods Pro 2. Nesil" [ref=e2]
  - text "12.999 TL" [ref=e3]
- region "Unrelated section" [ref=e4]
  - text "FULL_SNAPSHOT_SECRET_MARKER" [ref=e5]
""".strip()
    )

    result = manager._format_observation(
        observation,
        focus="RTX 5090",
        mode="focused",
    )

    assert "Snapshot mode: focused" in result
    assert "No sufficiently relevant page region was found" in result

    # The complete page must not leak into model context.
    assert "FULL_SNAPSHOT_SECRET_MARKER" not in result


def test_focus_hit_returns_focused_snapshot():
    manager = make_manager()

    observation = make_observation(
        """
- region "Products" [ref=e1]
  - group "AirPods Pro offer" [ref=e2]
    - link "Apple AirPods Pro 2. Nesil" [ref=e3]
    - text "12.999 TL" [ref=e4]
- region "Footer" [ref=e5]
  - text "UNRELATED_FOOTER_MARKER" [ref=e6]
""".strip()
    )

    result = manager._format_observation(
        observation,
        focus="AirPods Pro",
        mode="focused",
    )

    assert "Snapshot mode: focused" in result
    assert "Apple AirPods Pro 2. Nesil" in result
    assert "12.999 TL" in result

    # Focused snapshot should not contain unrelated page regions.
    assert "UNRELATED_FOOTER_MARKER" not in result


def test_focused_without_focus_never_falls_back_to_full_snapshot():
    manager = make_manager()

    observation = make_observation(
        """
- region "Products" [ref=e1]
  - text "FULL_MODE_SECRET_MARKER" [ref=e2]
""".strip()
    )

    result = manager._format_observation(
        observation,
        focus=None,
        mode="focused",
    )

    assert "Snapshot mode: focused" in result
    assert "No focus was provided" in result

    # Missing focus must not expose the complete page.
    assert "FULL_MODE_SECRET_MARKER" not in result


def test_full_snapshot_is_only_used_when_full_mode_is_requested():
    manager = make_manager()

    observation = make_observation(
        """
- region "Products" [ref=e1]
  - text "FULL_MODE_MARKER" [ref=e2]
""".strip()
    )

    result = manager._format_observation(
        observation,
        focus=None,
        mode="full",
    )

    assert "Snapshot mode: full" in result
    assert "FULL_MODE_MARKER" in result


def test_interactive_mode_returns_interactive_controls():
    manager = make_manager()

    observation = make_observation(
        """
- region "Flight search" [ref=e1]
  - textbox "Nereden" [ref=e2]
  - textbox "Nereye" [ref=e3]
  - button "Gidiş tarihi" [ref=e4]
  - button "Ucuz uçuş ara" [ref=e5]
- region "Footer" [ref=e6]
  - text "UNRELATED_INTERACTIVE_MARKER" [ref=e7]
""".strip()
    )

    result = manager._format_observation(
        observation,
        focus="Pegasus flight search form",
        mode="interactive",
    )

    assert "Snapshot mode: interactive" in result
    assert 'textbox "Nereden"' in result
    assert 'textbox "Nereye"' in result
    assert 'button "Gidiş tarihi"' in result
    assert 'button "Ucuz uçuş ara"' in result

    # Interactive mode should remove unrelated page content.
    assert "UNRELATED_INTERACTIVE_MARKER" not in result


def test_capture_snapshot_normalizes_and_remembers_mode():
    manager = BrowserManager(headless=True)

    captured = {}

    async def fake_capture_snapshot(*, focus=None, mode="focused"):
        captured["focus"] = focus
        captured["mode"] = mode
        return "TEST SNAPSHOT"

    manager._capture_snapshot = fake_capture_snapshot

    result = asyncio.run(
        manager.capture_snapshot(
            focus="Pegasus flight search form",
            mode="Interactive",
        )
    )

    assert result == "TEST SNAPSHOT"

    # Mode should be normalized before it is stored or forwarded.
    assert captured["mode"] == "interactive"
    assert manager._last_snapshot_mode == "interactive"

    # The latest meaningful focus should also be remembered.
    assert manager._last_snapshot_focus == "Pegasus flight search form"


def test_capture_snapshot_rejects_invalid_mode():
    manager = BrowserManager(headless=True)

    result = asyncio.run(
        manager.capture_snapshot(
            focus="Pegasus flight search form",
            mode="banana",
        )
    )

    assert "OBSERVATION FAILED" in result
    assert "Invalid snapshot mode" in result


def test_auto_observation_keeps_last_snapshot_mode():
    manager = BrowserManager(headless=True)

    manager._last_snapshot_focus = "Pegasus flight search form"
    manager._last_snapshot_mode = "interactive"

    captured = {}

    async def fake_capture_snapshot(*, focus=None, mode="focused"):
        captured["focus"] = focus
        captured["mode"] = mode
        return "INTERACTIVE AUTO OBSERVATION"

    manager._capture_snapshot = fake_capture_snapshot

    request = SimpleNamespace(
        name="browser_click",
        args={},
    )

    async def fake_handler(_request):
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text="Click completed.",
                )
            ],
            isError=False,
        )

    result = asyncio.run(
        manager._track_browser_action(
            request,
            fake_handler,
        )
    )

    assert captured["focus"] == "Pegasus flight search form"

    # Auto observation must keep the previous snapshot mode.
    assert captured["mode"] == "interactive"

    result_text = "\n".join(
        block.text
        for block in result.content
        if block.type == "text"
    )

    assert "AUTO CURRENT PAGE OBSERVATION" in result_text
    assert "INTERACTIVE AUTO OBSERVATION" in result_text