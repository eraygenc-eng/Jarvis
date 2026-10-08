
import unittest

from langchain_core.messages import AIMessage, ToolMessage

from core.browser_context import (
    compact_old_browser_snapshots,
    create_browser_context_middleware,
    extract_snapshot_metadata,
    get_recent_tool_group_indices,
    prune_old_completed_tool_groups,
)

from core.research.evidence import ObservationStore

from pydantic import PrivateAttr

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    ToolMessage,
)

from langchain_core.outputs import (
    ChatGeneration,
    ChatResult,
)

from core.browser_action_policy import current_observation_is_visible


class CapturingChatModel(BaseChatModel):
    _seen_messages: list = PrivateAttr(default_factory=list)

    @property
    def _llm_type(self):
        return "capturing-chat-model"

    @property
    def seen_messages(self):
        return self._seen_messages

    def bind_tools(
        self,
        tools,
        *,
        tool_choice=None,
        **kwargs,
    ):
        return self

    def _generate(
        self,
        messages,
        stop=None,
        run_manager=None,
        **kwargs,
    ):
        self._seen_messages = list(messages)

        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content="done"
                    )
                )
            ]
        )


class BrowserContextTests(unittest.IsolatedAsyncioTestCase):

    def _snapshot_message(
        self,
        observation,
        tool_call_id: str,
        page_text: str,
    ) -> ToolMessage:
        content = (
            f"Observation ID: {observation.observation_id}\n"
            f"Captured at: {observation.captured_at.isoformat()}\n"
            "This records page content, not a verified offer.\n\n"
            "### Page\n"
            f"- Page URL: {observation.page_url}\n"
            "### Snapshot\n"
            "```yaml\n"
            f"{page_text}\n"
            "```"
        )

        return ToolMessage(
            content=content,
            tool_call_id=tool_call_id,
            name="browser_snapshot",
        )

    def _auto_observation_message(
        self,
        observation,
        tool_call_id: str,
        page_text: str,
    ) -> ToolMessage:
        content = (
            "Clicked element successfully.\n\n"
            "AUTO CURRENT PAGE OBSERVATION\n"
            "A fresh browser observation was captured automatically.\n\n"
            f"Observation ID: {observation.observation_id}\n"
            f"Captured at: {observation.captured_at.isoformat()}\n"
            f"- Page URL: {observation.page_url}\n"
            "Snapshot mode: focused\n"
            "This records page content, not a verified offer.\n\n"
            "### Snapshot\n"
            "```yaml\n"
            f"{page_text}\n"
            "```"
        )

        return ToolMessage(
            content=content,
            tool_call_id=tool_call_id,
            name="browser_click",
        )

    def _assistant_call(
        self,
        tool_call_id: str,
    ) -> AIMessage:
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "browser_snapshot",
                    "args": {},
                    "id": tool_call_id,
                    "type": "tool_call",
                }
            ],
        )

    def test_extract_snapshot_metadata_reads_structured_auto_observation(self):
        # Simulate structured browser tool output.
        message = ToolMessage(
            content=[
                {
                    "type": "text",
                    "text": (
                        "Clicked element.\n\n"
                        "AUTO CURRENT PAGE OBSERVATION\n"
                        "Observation ID: obs-123\n"
                        "- Page URL: https://example.com/product\n"
                    ),
                }
            ],
            tool_call_id="call-structured",
            name="browser_click",
        )

        # Read metadata from the structured content.
        metadata = extract_snapshot_metadata(message)

        # The observation must be detected.
        self.assertIsNotNone(metadata)

        # Check the extracted values.
        self.assertEqual(
            metadata.observation_id,
            "obs-123",
        )

        self.assertEqual(
            metadata.page_url,
            "https://example.com/product",
        )

    def test_old_snapshot_is_compacted_but_recent_groups_are_preserved(self):
        store = ObservationStore()

        page_1 = "OLD SNAPSHOT DATA " * 400
        page_2 = "RECENT SNAPSHOT DATA " * 400
        page_3 = "CURRENT SNAPSHOT DATA " * 400

        observation_1 = store.capture(
            "https://example.com/old",
            page_1,
        )

        observation_2 = store.capture(
            "https://example.com/recent",
            page_2,
        )

        observation_3 = store.capture(
            "https://example.com/current",
            page_3,
        )

        messages = [
            self._assistant_call("call-1"),
            self._snapshot_message(
                observation_1,
                "call-1",
                page_1,
            ),
            self._assistant_call("call-2"),
            self._snapshot_message(
                observation_2,
                "call-2",
                page_2,
            ),
            self._assistant_call("call-3"),
            self._snapshot_message(
                observation_3,
                "call-3",
                page_3,
            ),
        ]

        old_original_content = messages[1].content
        recent_original_content = messages[3].content
        current_original_content = messages[5].content

        compacted = compact_old_browser_snapshots(
            messages,
            store,
        )

        # Old snapshot should be compacted.
        self.assertIn(
            "ARCHIVED BROWSER SNAPSHOT",
            compacted[1].content,
        )

        self.assertLess(
            len(compacted[1].content),
            len(old_original_content),
        )

        # Tool metadata must survive.
        self.assertEqual(
            compacted[1].tool_call_id,
            "call-1",
        )

        self.assertEqual(
            compacted[1].name,
            "browser_snapshot",
        )

        # Last two completed tool groups stay untouched.
        self.assertEqual(
            compacted[3].content,
            recent_original_content,
        )

        self.assertEqual(
            compacted[5].content,
            current_original_content,
        )

        # Raw history itself must not be mutated.
        self.assertEqual(
            messages[1].content,
            old_original_content,
        )

        # ObservationStore must still contain full evidence.
        self.assertEqual(
            store.get(
                observation_1.observation_id
            ).page_text,
            page_1,
        )

        # Current observation must remain unchanged.
        self.assertEqual(
            store.current_observation_id,
            observation_3.observation_id,
        )

    def test_old_auto_observation_is_compacted_without_losing_action_result(self):
        store = ObservationStore()

        old_page = "OLD AUTO OBSERVATION DATA " * 400
        recent_page = "RECENT SNAPSHOT DATA " * 400
        current_page = "CURRENT SNAPSHOT DATA " * 400

        old_observation = store.capture(
            "https://example.com/old-product",
            old_page,
        )

        recent_observation = store.capture(
            "https://example.com/recent",
            recent_page,
        )

        current_observation = store.capture(
            "https://example.com/current",
            current_page,
        )

        messages = [
            self._assistant_call("call-1"),
            self._auto_observation_message(
                old_observation,
                "call-1",
                old_page,
            ),
            self._assistant_call("call-2"),
            self._snapshot_message(
                recent_observation,
                "call-2",
                recent_page,
            ),
            self._assistant_call("call-3"),
            self._snapshot_message(
                current_observation,
                "call-3",
                current_page,
            ),
        ]

        original_content = messages[1].content

        compacted = compact_old_browser_snapshots(
            messages,
            store,
        )

        # The browser action result itself must survive.
        self.assertIn(
            "Clicked element successfully.",
            compacted[1].content,
        )

        # Only the embedded old observation should be archived.
        self.assertIn(
            "ARCHIVED AUTO BROWSER OBSERVATION",
            compacted[1].content,
        )

        # Large old page content should disappear from model input.
        self.assertNotIn(
            "OLD AUTO OBSERVATION DATA",
            compacted[1].content,
        )

        self.assertLess(
            len(compacted[1].content),
            len(original_content),
        )

        # Tool identity must remain a browser_click.
        self.assertEqual(
            compacted[1].name,
            "browser_click",
        )

        self.assertEqual(
            compacted[1].tool_call_id,
            "call-1",
        )

        # Full evidence must still exist outside model context.
        self.assertEqual(
            store.get(
                old_observation.observation_id
            ).page_text,
            old_page,
        )

        # Current observation remains the newest one.
        self.assertEqual(
            store.current_observation_id,
            current_observation.observation_id,
        )

    def test_current_auto_observation_is_not_compacted(self):
        store = ObservationStore()

        page = "CURRENT AUTO OBSERVATION DATA " * 400

        observation = store.capture(
            "https://example.com/current-product",
            page,
        )

        messages = [
            self._assistant_call("call-1"),
            self._auto_observation_message(
                observation,
                "call-1",
                page,
            ),
        ]

        original_content = messages[1].content

        compacted = compact_old_browser_snapshots(
            messages,
            store,
        )

        self.assertEqual(
            compacted[1].content,
            original_content,
        )

        self.assertNotIn(
            "ARCHIVED AUTO BROWSER OBSERVATION",
            compacted[1].content,
        )

        self.assertIn(
            "CURRENT AUTO OBSERVATION DATA",
            compacted[1].content,
        )

    def test_policy_keeps_snapshot_available_after_structured_auto_observation(self):
        store = ObservationStore()

        # Create the current browser observation.
        observation = store.capture(
            "https://example.com/product",
            "PRODUCT PAGE DATA",
        )

        # Simulate structured browser tool output.
        message = ToolMessage(
            content=[
                {
                    "type": "text",
                    "text": (
                        "Clicked element.\n\n"
                        "AUTO CURRENT PAGE OBSERVATION\n"
                        f"Observation ID: {observation.observation_id}\n"
                        "- Page URL: https://example.com/product\n"
                    ),
                }
            ],
            tool_call_id="call-policy",
            name="browser_click",
        )

        # An explicit snapshot should remain available after an auto observation.
        visible = current_observation_is_visible(
            [message],
            store,
        )

        self.assertFalse(visible)

    def test_policy_reads_structured_explicit_snapshot(self):
        # Store a real page observation.
        store = ObservationStore()

        observation = store.capture(
            "https://example.com/product",
            "Product page data",
        )

        # Simulate a structured snapshot tool result.
        message = ToolMessage(
            content=[
                {
                    "type": "text",
                    "text": (
                        f"Observation ID: {observation.observation_id}\n"
                        "- Page URL: https://example.com/product\n"
                        "### Snapshot\n"
                        "Product page data"
                    ),
                }
            ],
            tool_call_id="call-explicit",
            name="browser_snapshot",
        )

        # A valid explicit snapshot should be recognized.
        visible = current_observation_is_visible(
            [message],
            store,
        )

        self.assertTrue(visible)

    async def test_middleware_compacts_only_model_request(self):
        store = ObservationStore()

        page_1 = "OLD SNAPSHOT DATA " * 400
        page_2 = "RECENT SNAPSHOT DATA " * 400
        page_3 = "CURRENT SNAPSHOT DATA " * 400

        observation_1 = store.capture(
            "https://example.com/old",
            page_1,
        )

        observation_2 = store.capture(
            "https://example.com/recent",
            page_2,
        )

        observation_3 = store.capture(
            "https://example.com/current",
            page_3,
        )

        messages = [
            self._assistant_call("call-1"),
            self._snapshot_message(
                observation_1,
                "call-1",
                page_1,
            ),
            self._assistant_call("call-2"),
            self._snapshot_message(
                observation_2,
                "call-2",
                page_2,
            ),
            self._assistant_call("call-3"),
            self._snapshot_message(
                observation_3,
                "call-3",
                page_3,
            ),
        ]

        original_old_content = messages[1].content

        class FakeRequest:
            def __init__(self, messages):
                self.messages = messages

            def override(self, **overrides):
                return FakeRequest(
                    overrides.get(
                        "messages",
                        self.messages,
                    )
                )

        captured = {}

        async def handler(request):
            captured["request"] = request
            return "model-result"

        middleware = create_browser_context_middleware(
            store
        )

        result = await middleware.awrap_model_call(
            FakeRequest(messages),
            handler,
        )

        self.assertEqual(
            result,
            "model-result",
        )

        model_messages = captured[
            "request"
        ].messages

        # The model receives the compacted old snapshot.
        self.assertIn(
            "ARCHIVED BROWSER SNAPSHOT",
            model_messages[1].content,
        )

        # The original history remains untouched.
        self.assertEqual(
            messages[1].content,
            original_old_content,
        )

        # Recent/current snapshots remain complete.
        self.assertNotIn(
            "ARCHIVED BROWSER SNAPSHOT",
            model_messages[3].content,
        )

        self.assertNotIn(
            "ARCHIVED BROWSER SNAPSHOT",
            model_messages[5].content,
        )

    async def test_real_agent_graph_compacts_old_snapshot_before_model(self):
        store = ObservationStore()

        page_1 = "OLD SNAPSHOT DATA " * 400
        page_2 = "RECENT SNAPSHOT DATA " * 400
        page_3 = "CURRENT SNAPSHOT DATA " * 400

        observation_1 = store.capture(
            "https://example.com/old",
            page_1,
        )

        observation_2 = store.capture(
            "https://example.com/recent",
            page_2,
        )

        observation_3 = store.capture(
            "https://example.com/current",
            page_3,
        )

        history = [
            self._assistant_call("call-1"),
            self._snapshot_message(
                observation_1,
                "call-1",
                page_1,
            ),
            self._assistant_call("call-2"),
            self._snapshot_message(
                observation_2,
                "call-2",
                page_2,
            ),
            self._assistant_call("call-3"),
            self._snapshot_message(
                observation_3,
                "call-3",
                page_3,
            ),
            HumanMessage(
                content="Continue the research."
            ),
        ]

        model = CapturingChatModel()

        middleware = create_browser_context_middleware(
            store
        )

        graph = create_agent(
            model=model,
            tools=[],
            middleware=[
                middleware,
            ],
        )

        result = await graph.ainvoke(
            {
                "messages": history,
            }
        )

        self.assertEqual(
            result["messages"][-1].content,
            "done",
        )

        seen = model.seen_messages

        old_snapshot = next(
            message
            for message in seen
            if (
                isinstance(message, ToolMessage)
                and message.tool_call_id == "call-1"
            )
        )

        recent_snapshot = next(
            message
            for message in seen
            if (
                isinstance(message, ToolMessage)
                and message.tool_call_id == "call-2"
            )
        )

        current_snapshot = next(
            message
            for message in seen
            if (
                isinstance(message, ToolMessage)
                and message.tool_call_id == "call-3"
            )
        )

        # The real graph sends the old snapshot compacted.
        self.assertIn(
            "ARCHIVED BROWSER SNAPSHOT",
            old_snapshot.content,
        )

        # Recent groups remain untouched.
        self.assertNotIn(
            "ARCHIVED BROWSER SNAPSHOT",
            recent_snapshot.content,
        )

        self.assertNotIn(
            "ARCHIVED BROWSER SNAPSHOT",
            current_snapshot.content,
        )

        # Full archived evidence still exists outside model input.
        self.assertEqual(
            store.get(
                observation_1.observation_id
            ).page_text,
            page_1,
        )

    def test_old_completed_tool_groups_are_pruned_only_after_threshold(self):
        store = ObservationStore()

        messages = []

        for number in range(1, 10):
            page = f"SNAPSHOT {number} " * 400

            observation = store.capture(
                f"https://example.com/{number}",
                page,
            )

            call_id = f"call-{number}"

            messages.extend([
                self._assistant_call(call_id),
                self._snapshot_message(
                    observation,
                    call_id,
                    page,
                ),
            ])

        original_length = len(messages)

        pruned = prune_old_completed_tool_groups(
            messages,
            store,
        )

        # Raw history is untouched.
        self.assertEqual(
            len(messages),
            original_length,
        )

        # With 9 completed groups and keep_count=4, only the newest
        # four groups remain model-facing.
        self.assertEqual(
            len(pruned),
            8,
        )

        remaining_ids = {
            message.tool_call_id
            for message in pruned
            if isinstance(message, ToolMessage)
        }

        self.assertEqual(
            remaining_ids,
            {
                "call-6",
                "call-7",
                "call-8",
                "call-9",
            },
        )

        # The current observation is the newest snapshot and remains intact.
        current_snapshot = next(
            message
            for message in pruned
            if (
                isinstance(message, ToolMessage)
                and message.tool_call_id == "call-9"
            )
        )

        self.assertNotIn(
            "ARCHIVED BROWSER SNAPSHOT",
            current_snapshot.content,
        )

    def test_incomplete_multi_tool_group_is_protected(self):
        messages = [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "browser_snapshot",
                        "args": {},
                        "id": "snapshot-call",
                        "type": "tool_call",
                    },
                    {
                        "name": "research_status",
                        "args": {},
                        "id": "status-call",
                        "type": "tool_call",
                    },
                ],
            ),
            ToolMessage(
                content="snapshot response",
                tool_call_id="snapshot-call",
                name="browser_snapshot",
            ),
        ]

        protected = get_recent_tool_group_indices(
            messages,
            group_count=2,
        )

        self.assertEqual(
            protected,
            {0, 1},
        )


if __name__ == "__main__":
    unittest.main()
