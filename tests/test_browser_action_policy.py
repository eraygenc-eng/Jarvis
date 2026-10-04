from types import SimpleNamespace

from langchain_core.messages import ToolMessage

from core.browser_action_policy import (
    current_observation_is_visible,
    filter_browser_action_tools,
)


def test_no_current_observation_returns_false():
    # Browser has no current observation
    observation_store = SimpleNamespace(
        current_observation_id=None
    )

    result = current_observation_is_visible(
        messages=[],
        observation_store=observation_store,
    )

    assert result is False


def test_current_observation_in_history_returns_true():
    # Browser has a current observation
    observation_store = SimpleNamespace(
        current_observation_id="obs-123"
    )

    # Model history contains the same usable observation
    messages = [
        ToolMessage(
            content=(
                "Observation ID: obs-123\n"
                "- Page URL: https://example.com\n"
                "Snapshot mode: focused\n"
                "### Snapshot\n"
                "FOCUSED BROWSER SNAPSHOT\n"
                '- text "1.398 TL" [ref=e1]'
            ),
            tool_call_id="call-1",
            name="browser_snapshot",
        )
    ]

    result = current_observation_is_visible(
        messages=messages,
        observation_store=observation_store,
    )

    assert result is True


def test_old_observation_does_not_count_as_current():
    # Browser has a newer current observation
    observation_store = SimpleNamespace(
        current_observation_id="obs-999"
    )

    # Model history only contains an older observation
    messages = [
        ToolMessage(
            content=(
                "Observation ID: obs-123\n"
                "- Page URL: https://example.com\n"
                "Snapshot mode: focused\n"
                "### Snapshot\n"
                "FOCUSED BROWSER SNAPSHOT\n"
                '- text "Old result" [ref=e1]'
            ),
            tool_call_id="call-1",
            name="browser_snapshot",
        )
    ]

    result = current_observation_is_visible(
        messages=messages,
        observation_store=observation_store,
    )

    assert result is False


def test_auto_observation_does_not_hide_explicit_snapshot():
    # Browser has a current observation
    observation_store = SimpleNamespace(
        current_observation_id="obs-456"
    )

    # Navigation returned a usable automatic observation
    messages = [
        ToolMessage(
            content=(
                "Navigation completed.\n\n"
                "AUTO CURRENT PAGE OBSERVATION\n"
                "Observation ID: obs-456\n"
                "- Page URL: https://example.com/product\n"
                "Snapshot mode: interactive\n"
                "### Snapshot\n"
                "INTERACTIVE BROWSER SNAPSHOT\n"
                '- button "Search" [ref=e1]'
            ),
            tool_call_id="call-2",
            name="browser_navigate",
        )
    ]

    result = current_observation_is_visible(
        messages=messages,
        observation_store=observation_store,
    )

    # Auto observations must not block a new explicit snapshot.
    assert result is False


def test_unusable_focused_snapshot_does_not_count_as_visible():
    # Browser has a current observation
    observation_store = SimpleNamespace(
        current_observation_id="obs-focused"
    )

    # The snapshot exists, but focused extraction failed
    messages = [
        ToolMessage(
            content=(
                "Observation ID: obs-focused\n"
                "- Page URL: https://www.flypgs.com/\n"
                "Snapshot mode: focused\n"
                "### Snapshot\n"
                "FOCUSED BROWSER SNAPSHOT\n"
                "Focus: Pegasus flight search form\n\n"
                "No sufficiently relevant page region was found "
                "for this focus."
            ),
            tool_call_id="call-focused",
            name="browser_snapshot",
        )
    ]

    result = current_observation_is_visible(
        messages=messages,
        observation_store=observation_store,
    )

    # The model must be allowed to request another snapshot.
    assert result is False


def test_unusable_interactive_snapshot_does_not_count_as_visible():
    # Browser has a current observation
    observation_store = SimpleNamespace(
        current_observation_id="obs-interactive"
    )

    # Interactive extraction found no usable controls
    messages = [
        ToolMessage(
            content=(
                "Observation ID: obs-interactive\n"
                "- Page URL: https://www.flypgs.com/\n"
                "Snapshot mode: interactive\n"
                "### Snapshot\n"
                "INTERACTIVE BROWSER SNAPSHOT\n\n"
                "No interactive controls were found on the current page."
            ),
            tool_call_id="call-interactive",
            name="browser_snapshot",
        )
    ]

    result = current_observation_is_visible(
        messages=messages,
        observation_store=observation_store,
    )

    # The model must still be able to request another snapshot.
    assert result is False


def test_tools_are_kept_when_current_observation_is_not_visible():
    # Create simple fake tools
    tools = [
        SimpleNamespace(name="browser_snapshot"),
        SimpleNamespace(name="browser_navigate"),
        SimpleNamespace(name="browser_find"),
    ]

    result = filter_browser_action_tools(
        tools,
        current_observation_visible=False,
    )

    # No tool should be removed
    assert len(result) == 3

    names = [tool.name for tool in result]

    assert "browser_snapshot" in names
    assert "browser_navigate" in names
    assert "browser_find" in names


def test_snapshot_is_hidden_when_current_observation_is_visible():
    # Create simple fake tools
    tools = [
        SimpleNamespace(name="browser_snapshot"),
        SimpleNamespace(name="browser_navigate"),
        SimpleNamespace(name="browser_find"),
    ]

    result = filter_browser_action_tools(
        tools,
        current_observation_visible=True,
    )

    names = [tool.name for tool in result]

    # Snapshot should be hidden
    assert "browser_snapshot" not in names

    # Other browser tools should stay available
    assert "browser_navigate" in names
    assert "browser_find" in names