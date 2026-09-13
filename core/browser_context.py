import re

from dataclasses import dataclass

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    ToolMessage,
)

from langchain.agents.middleware import wrap_model_call


SNAPSHOT_TRIM_THRESHOLD = 4000

# Start removing old completed tool groups only after history becomes
# meaningfully large. Short interactions keep their full tool history.
TOOL_GROUP_PRUNE_THRESHOLD = 8

# Keep enough recent completed groups for local reasoning while old durable
# research/browser state remains available outside model history.
TOOL_GROUP_KEEP_COUNT = 4


@dataclass(frozen=True)
class SnapshotMetadata:
    observation_id: str
    page_url: str


def extract_snapshot_metadata(
    message: ToolMessage,
) -> SnapshotMetadata | None:
    """Read trusted metadata from a browser_snapshot ToolMessage."""

    if message.name != "browser_snapshot":
        return None

    if not isinstance(message.content, str):
        return None

    observation_match = re.search(
        r"(?m)^Observation ID:\s*(\S+)\s*$",
        message.content,
    )

    url_match = re.search(
        r"(?m)^- Page URL:\s*(https?://[^\s]+)\s*$",
        message.content,
    )

    if observation_match is None or url_match is None:
        return None

    return SnapshotMetadata(
        observation_id=observation_match.group(1),
        page_url=url_match.group(1),
    )


def compact_snapshot_message(
    message: ToolMessage,
    metadata: SnapshotMetadata,
) -> ToolMessage:
    """Return a compact model-facing copy of an old snapshot."""

    compact_content = (
        "ARCHIVED BROWSER SNAPSHOT\n"
        f"Observation ID: {metadata.observation_id}\n"
        f"Page URL: {metadata.page_url}\n"
        "The full old page content was removed from model input.\n"
        "This is archived evidence, not current browser evidence.\n"
        "Use research_read_observation if the archived page must be inspected again."
    )

    return message.model_copy(
        update={
            "content": compact_content,
        }
    )




def _collect_tool_groups(
    messages: list[BaseMessage],
) -> tuple[list[set[int]], list[set[int]]]:
    """Collect completed and incomplete AI tool-call groups."""

    completed_groups: list[set[int]] = []
    incomplete_groups: list[set[int]] = []

    for index, message in enumerate(messages):
        if not isinstance(message, AIMessage):
            continue

        tool_calls = getattr(message, "tool_calls", None) or []

        tool_call_ids = {
            str(call["id"])
            for call in tool_calls
            if (
                isinstance(call, dict)
                and call.get("id")
            )
        }

        if not tool_call_ids:
            continue

        group_indices = {index}
        answered_ids = set()

        for tool_index in range(index + 1, len(messages)):
            tool_message = messages[tool_index]

            if not isinstance(tool_message, ToolMessage):
                break

            if tool_message.tool_call_id in tool_call_ids:
                group_indices.add(tool_index)
                answered_ids.add(tool_message.tool_call_id)

        if answered_ids == tool_call_ids:
            completed_groups.append(group_indices)
        else:
            incomplete_groups.append(group_indices)

    return completed_groups, incomplete_groups


def _protect_group_containing_index(
    groups: list[set[int]],
    protected_indices: set[int],
    target_index: int | None,
) -> None:
    """Protect an entire tool group when one of its messages must survive."""

    if target_index is None:
        return

    for group in groups:
        if target_index in group:
            protected_indices.update(group)
            return


def prune_old_completed_tool_groups(
    messages: list[BaseMessage],
    observation_store,
    *,
    prune_threshold: int = TOOL_GROUP_PRUNE_THRESHOLD,
    keep_count: int = TOOL_GROUP_KEEP_COUNT,
) -> list[BaseMessage]:
    """Remove old completed tool groups from model input only.

    Durable research state stays in ComparisonState and full archived browser
    observations stay in ObservationStore. Recent groups, incomplete groups,
    the latest snapshot, and the current observation are preserved.

    Whole AI-tool-call groups are removed together with their ToolMessages so
    the model never receives orphaned tool calls or orphaned tool responses.
    """

    if not messages:
        return messages

    completed_groups, incomplete_groups = _collect_tool_groups(messages)

    # Keep short interactions untouched.
    if len(completed_groups) <= prune_threshold:
        return list(messages)

    all_groups = completed_groups + incomplete_groups
    protected_indices: set[int] = set()

    # Keep the most recent completed groups.
    for group in completed_groups[-keep_count:]:
        protected_indices.update(group)

    # Never prune an incomplete tool call sequence.
    for group in incomplete_groups:
        protected_indices.update(group)

    # Protect the newest explicit browser snapshot together with its AI call.
    latest_snapshot_index = None

    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]

        if (
            isinstance(message, ToolMessage)
            and message.name == "browser_snapshot"
        ):
            latest_snapshot_index = index
            break

    _protect_group_containing_index(
        all_groups,
        protected_indices,
        latest_snapshot_index,
    )

    # Protect the current observation together with its AI call, even if a
    # later non-current snapshot exists for some unusual reason.
    current_observation_id = observation_store.current_observation_id

    if current_observation_id is not None:
        for index, message in enumerate(messages):
            if not isinstance(message, ToolMessage):
                continue

            metadata = extract_snapshot_metadata(message)

            if (
                metadata is not None
                and metadata.observation_id == current_observation_id
            ):
                _protect_group_containing_index(
                    all_groups,
                    protected_indices,
                    index,
                )

    remove_indices: set[int] = set()

    for group in completed_groups:
        if group & protected_indices:
            continue

        remove_indices.update(group)

    if not remove_indices:
        return list(messages)

    return [
        message
        for index, message in enumerate(messages)
        if index not in remove_indices
    ]

def get_recent_tool_group_indices(
    messages: list[BaseMessage],
    group_count: int = 2,
) -> set[int]:
    """Protect recent completed groups and the latest incomplete tool group."""

    completed_groups: list[set[int]] = []
    latest_incomplete_group: set[int] = set()

    for index, message in enumerate(messages):
        if not isinstance(message, AIMessage):
            continue

        tool_calls = getattr(message, "tool_calls", None) or []

        tool_call_ids = {
            str(call["id"])
            for call in tool_calls
            if (
                isinstance(call, dict)
                and call.get("id")
            )
        }

        if not tool_call_ids:
            continue

        group_indices = {index}
        answered_ids = set()

        for tool_index in range(index + 1, len(messages)):
            tool_message = messages[tool_index]

            if not isinstance(tool_message, ToolMessage):
                break

            if tool_message.tool_call_id in tool_call_ids:
                group_indices.add(tool_index)
                answered_ids.add(
                    tool_message.tool_call_id
                )

        if answered_ids == tool_call_ids:
            completed_groups.append(
                group_indices
            )
        else:
            latest_incomplete_group = (
                group_indices
            )

    protected: set[int] = set()

    for group in completed_groups[-group_count:]:
        protected.update(group)

    protected.update(
        latest_incomplete_group
    )

    return protected



def compact_old_browser_snapshots(
    messages: list[BaseMessage],
    observation_store,
) -> list[BaseMessage]:
    """Compact only old, large, safely recoverable browser snapshots."""

    if not messages:
        return messages

    protected_indices = get_recent_tool_group_indices(
        messages,
        group_count=2,
    )

    # Always protect the newest explicit browser_snapshot.
    latest_snapshot_index = None

    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]

        if (
            isinstance(message, ToolMessage)
            and message.name == "browser_snapshot"
        ):
            latest_snapshot_index = index
            protected_indices.add(index)
            break

    current_observation_id = (
        observation_store.current_observation_id
    )

    compacted_messages = list(messages)

    for index, message in enumerate(messages):
        if index in protected_indices:
            continue

        if not isinstance(message, ToolMessage):
            continue

        metadata = extract_snapshot_metadata(message)

        if metadata is None:
            continue

        # Keep short snapshots unchanged.
        if len(message.content) <= SNAPSHOT_TRIM_THRESHOLD:
            continue

        # Keep the current observation unchanged.
        if (
            current_observation_id is not None
            and metadata.observation_id
            == current_observation_id
        ):
            continue

        # Only compact snapshots whose full evidence still exists.
        stored_observation = observation_store.get(
            metadata.observation_id
        )

        if stored_observation is None:
            continue

        # The archived ID and URL must still agree.
        if stored_observation.page_url != metadata.page_url:
            continue

        compacted_messages[index] = (
            compact_snapshot_message(
                message,
                metadata,
            )
        )

    return compacted_messages



def create_browser_context_middleware(
    observation_store,
):
    """Create middleware that trims old snapshots only for model input."""

    @wrap_model_call
    async def browser_context_middleware(
        request,
        handler,
    ):
        compacted_messages = compact_old_browser_snapshots(
            request.messages,
            observation_store,
        )

        model_messages = prune_old_completed_tool_groups(
            compacted_messages,
            observation_store,
        )

        model_request = request.override(
            messages=model_messages,
        )

        return await handler(model_request)

    return browser_context_middleware