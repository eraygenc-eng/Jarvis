from datetime import datetime, timezone
from types import SimpleNamespace

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
    )

    assert "Snapshot mode: focused" in result
    assert "No sufficiently relevant page region was found" in result

    # Most important guarantee:
    # the complete page must not leak into model context.
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
    )

    assert "Snapshot mode: focused" in result
    assert "Apple AirPods Pro 2. Nesil" in result
    assert "12.999 TL" in result

    # Focused snapshot should not contain unrelated page regions.
    assert "UNRELATED_FOOTER_MARKER" not in result


def test_full_snapshot_is_only_used_without_focus():
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
    )

    assert "Snapshot mode: full" in result
    assert "FULL_MODE_MARKER" in result