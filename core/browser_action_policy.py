from langchain_core.messages import ToolMessage
from core.browser_context import extract_snapshot_metadata



def _snapshot_is_usable(message: ToolMessage) -> bool:
    # Snapshot content must be useful for the next browser decision.
    if not isinstance(message.content, str):
        return False

    unusable_markers = {
        "No sufficiently relevant page region was found",
        "No interactive controls were found",
        "No focus was provided",
        "OBSERVATION FAILED:",
        "OBSERVATION NOT STORED:",
    }

    return not any(
        marker in message.content
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
        if (
            isinstance(message.content, str)
            and "AUTO CURRENT PAGE OBSERVATION" in message.content
        ):
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