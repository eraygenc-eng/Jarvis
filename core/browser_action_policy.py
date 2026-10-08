from langchain_core.messages import ToolMessage
from core.browser_context import extract_snapshot_metadata



def _message_text(message: ToolMessage) -> str:
    # Browser tool results can contain text or content blocks.
    content = message.content

    if isinstance(content, str):
        return content

    if not isinstance(content, list):
        return ""

    parts = []

    for block in content:
        if isinstance(block, str):
            parts.append(block)

        elif isinstance(block, dict):
            block_text = block.get("text")

            if isinstance(block_text, str):
                parts.append(block_text)

    return "\n".join(parts)


def _snapshot_is_usable(message: ToolMessage) -> bool:
    # Check the actual text of the browser observation.
    text = _message_text(message)

    if not text.strip():
        return False

    unusable_markers = {
        "No sufficiently relevant page region was found",
        "No interactive controls were found",
        "No focus was provided",
        "OBSERVATION FAILED:",
        "OBSERVATION NOT STORED:",
    }

    return not any(
        marker in text
        for marker in unusable_markers
    )



def current_observation_is_visible(messages, observation_store) -> bool:
    # Get current browser observation
    current_observation_id = observation_store.current_observation_id

    if current_observation_id is None:
        return False


    # Check newest messages first
    for message in reversed(messages or []):
        if not isinstance(message, ToolMessage):
            continue

        # Show the browser tool message content type
        print(
            "[BrowserActionPolicyDebug] "
            f"tool={message.name} "
            f"content_type={type(message.content).__name__}"
        )

        # Read browser observ metada
        metada = extract_snapshot_metadata(message)

        if metada is None:
            continue

        # Ignore older browser observs
        if metada.observation_id != current_observation_id:
            continue

        # Auto observations should not block an explicit snapshot.
        # The model may need to switch snapshot mode after the page changes.
        if "AUTO CURRENT PAGE OBSERVATION" in _message_text(message):
            continue

        # Don't hide browser_snapshot when the current view is unusable
        if not _snapshot_is_usable(message):
            print(
                "[BrowserActionPolicy] "
                "current observation is not usable"
            )
            return False
        
        return True

    return False


def filter_browser_action_tools(tools, *, current_observation_visible: bool):
    # Conver tools to normal list
    tools = list(tools or [])

    # Keep all tools when there is no reusable observation
    if not current_observation_visible:
        return tools


    # Hide snapshot when the current page is already visible
    return [
        tool
        for tool in tools
        if getattr(tool, "name", None) != "browser_snapshot" # Safely get an attribute; return the default value if it does not exist
    ]