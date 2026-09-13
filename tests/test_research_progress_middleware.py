import unittest

from types import SimpleNamespace

from pydantic import PrivateAttr

from langchain.agents import create_agent

from langchain_core.language_models.chat_models import (
    BaseChatModel,
)

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
)

from langchain_core.outputs import (
    ChatGeneration,
    ChatResult,
)

from core.context import RequestContext

from core.research.comparison_state import (
    ComparisonState,
    SourceStatus,
)

from core.research.progress_middleware import (
    create_research_progress_middleware,
)


class CapturingChatModel(BaseChatModel):
    _seen_messages: list = PrivateAttr(
        default_factory=list
    )

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


class FakeRequest:

    def __init__(
        self,
        messages,
        research_active=True,
    ):
        self.messages = messages

        self.runtime = SimpleNamespace(
            context=SimpleNamespace(
                research_active=research_active,
            )
        )

    def override(
        self,
        **overrides,
    ):
        request = FakeRequest(
            overrides.get(
                "messages",
                self.messages,
            ),
            research_active=(
                self.runtime.context.research_active
            ),
        )

        return request


class ResearchProgressMiddlewareTests(
    unittest.IsolatedAsyncioTestCase
):

    def make_state(self):
        state = ComparisonState(
            query=(
                "Logitech Superlight 2 "
                "en ucuzunu bul"
            ),
            planned_sources=[
                "Finished",
                "Active",
                "Next",
            ],
        )

        state.get_source_state(
            "Finished"
        ).status = SourceStatus.NO_RESULTS

        state.get_source_state(
            "Active"
        ).status = SourceStatus.RESEARCHING

        return state

    async def test_progress_is_injected_only_into_model_request(
        self,
    ):
        state = self.make_state()

        middleware = (
            create_research_progress_middleware(
                lambda: state
            )
        )

        original_messages = [
            HumanMessage(
                content="Find the cheapest option."
            )
        ]

        captured = {}

        async def handler(request):
            captured["messages"] = (
                list(request.messages)
            )

            return "model-result"

        result = await middleware.awrap_model_call(
            FakeRequest(original_messages),
            handler,
        )

        self.assertEqual(
            result,
            "model-result",
        )

        # Original history must remain untouched.
        self.assertEqual(
            len(original_messages),
            1,
        )

        model_messages = captured["messages"]

        self.assertEqual(
            len(model_messages),
            2,
        )

        progress_message = model_messages[-1]

        self.assertIsInstance(
            progress_message,
            HumanMessage,
        )

        self.assertIn(
            "INTERNAL RESEARCH PROGRESS",
            progress_message.content,
        )

        self.assertIn(
            '"action":"continue_source"',
            progress_message.content,
        )

        self.assertIn(
            '"source":"Active"',
            progress_message.content,
        )

    async def test_normal_chat_gets_no_progress_message(
        self,
    ):
        state = self.make_state()

        middleware = (
            create_research_progress_middleware(
                lambda: state
            )
        )

        messages = [
            HumanMessage(
                content="Hello"
            )
        ]

        captured = {}

        async def handler(request):
            captured["messages"] = (
                list(request.messages)
            )

            return "done"

        await middleware.awrap_model_call(
            FakeRequest(
                messages,
                research_active=False,
            ),
            handler,
        )

        self.assertEqual(
            captured["messages"],
            messages,
        )

    async def test_progress_refreshes_after_state_changes(
        self,
    ):
        state = self.make_state()

        middleware = (
            create_research_progress_middleware(
                lambda: state
            )
        )

        messages = [
            HumanMessage(
                content="Continue."
            )
        ]

        captured = []

        async def handler(request):
            captured.append(
                request.messages[-1].content
            )

            return "done"

        await middleware.awrap_model_call(
            FakeRequest(messages),
            handler,
        )

        self.assertIn(
            '"action":"continue_source"',
            captured[-1],
        )

        self.assertIn(
            '"source":"Active"',
            captured[-1],
        )

        # Active source finishes.
        state.get_source_state(
            "Active"
        ).status = SourceStatus.NO_RESULTS

        await middleware.awrap_model_call(
            FakeRequest(messages),
            handler,
        )

        # The next model call must immediately see the updated state.
        self.assertIn(
            '"action":"start_source"',
            captured[-1],
        )

        self.assertIn(
            '"source":"Next"',
            captured[-1],
        )

    async def test_real_agent_sees_progress_but_history_does_not(
        self,
    ):
        state = self.make_state()

        model = CapturingChatModel()

        middleware = (
            create_research_progress_middleware(
                lambda: state
            )
        )

        graph = create_agent(
            model=model,
            tools=[],
            context_schema=RequestContext,
            middleware=[
                middleware,
            ],
        )

        context = RequestContext(
            user_message=state.query,
            research_active=True,
        )

        result = await graph.ainvoke(
            {
                "messages": [
                    HumanMessage(
                        content=state.query
                    )
                ]
            },
            context=context,
        )

        seen_progress = [
            message
            for message in model.seen_messages
            if (
                isinstance(
                    message,
                    HumanMessage,
                )
                and "INTERNAL RESEARCH PROGRESS"
                in str(message.content)
            )
        ]

        self.assertEqual(
            len(seen_progress),
            1,
        )

        self.assertIn(
            '"action":"continue_source"',
            seen_progress[0].content,
        )

        # Ephemeral progress must not be persisted into graph history.
        persisted_progress = [
            message
            for message in result["messages"]
            if (
                isinstance(
                    message,
                    HumanMessage,
                )
                and "INTERNAL RESEARCH PROGRESS"
                in str(message.content)
            )
        ]

        self.assertEqual(
            persisted_progress,
            [],
        )


if __name__ == "__main__":
    unittest.main()