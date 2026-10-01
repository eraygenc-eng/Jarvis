from langchain_core.messages import ToolMessage
from core.browser_context import extract_snapshot_metadata



def current_observation_is_visible(messages, observation_store) -> bool:
    # Get current browser observation
    current_observation_id = (observation_store.current_observation_id)

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

        # Check if this is the current observation
        if metada.observation_id == current_observation_id:
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