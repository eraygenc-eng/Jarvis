import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from pydantic import PrivateAttr

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from core.research.comparison_state import (
    ComparisonResult, ComparisonState, SourceStatus, VerificationStatus,
)
from core.research.evidence import ObservationStore
from core.research.offer_verification import OfferQuote
from core.research.ranking import (
    find_best_overall, find_best_conditional, get_public_total,
    get_unverified_source_winners, normalize_currency,
)
from core.research.research_tools import create_research_tools
from core.research.verification import urls_match, validate_money_values
from core.research.task_classifier import TaskType, classify_task
from core.research.source_planner import ResearchCategory, plan_sources


SCOPES = {
    "product": "Desk lamp, model L2, one item",
    "flight": "IST to BER, 2026-11-10, two adults, economy, checked baggage included",
    "hotel": "2026-11-10 to 2026-11-13, three nights, one double room, two adults",
    "car_rental": "2026-11-10 to 2026-11-13, compact, unlimited mileage, same pickup and return",
}


class CountingChatModel(BaseChatModel):
    _call_count: int = PrivateAttr(default=0)

    @property
    def call_count(self):
        return self._call_count

    @property
    def _llm_type(self):
        return "counting-chat-model"

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        return self

    def _generate(
        self,
        messages,
        stop=None,
        run_manager=None,
        **kwargs,
    ):
        self._call_count += 1

        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(content="model response")
                )
            ]
        )


def snapshot_and_quote(category="product", price=6000, **overrides):
    amount = f"{price:.2f}"
    scope = SCOPES[category]
    text = (
        '- article [ref=offer]:\n'
        f'  - heading [ref=identity]: {scope}\n'
        '  - generic [ref=seller]: Example Provider\n'
        f'  - generic [ref=price]: Price: {amount} TRY\n'
        f'  - generic [ref=scope]: Full request: {scope}\n'
        '  - generic [ref=fees]: All mandatory fees included\n'
        '  - generic [ref=member]: Paid members only\n'
        '  - generic [ref=extra]: Mandatory fees: 120.00 TRY\n'
        '  - generic [ref=shipping]: Free shipping\n'
    )
    values = dict(
        offer_ref="offer", identity_evidence=scope,
        seller="Example Provider", seller_evidence="Example Provider",
        currency="TRY", price_evidence=f'- generic [ref=price]: Price: {amount} TRY',
        price_amount_texts={"price": amount}, price_decimal_separator=".", price=price,
        price_scope="total", scope_evidence=f"Full request: {scope}",
        fees_included=True, fees_evidence="All mandatory fees included",
    )
    values.update(overrides)
    return text, values


class ResearchFixture:
    def __init__(self, category="product"):
        self.category = category
        self.state = ComparisonState(query="Find the cheapest matching option", category=category,
                                     planned_sources=["Discovery"])
        self.result = ComparisonResult(title=SCOPES[category], source="Discovery",
                                       price=4500, currency="TRY", seller="Example Provider",
                                       offer_url="https://merchant.example/offer", url="https://discovery.example/item")
        self.state.add_result(self.result)
        self.store = ObservationStore()
        self.tools = {tool.name: tool for tool in create_research_tools(lambda: self.state, self.store)}

    def capture(self, price=6000, **overrides):
        text, quote = snapshot_and_quote(self.category, price, **overrides)
        observation = self.store.capture(self.result.offer_url, text)
        return {"result_id": self.result.result_id, "observation_id": observation.observation_id, "quote": quote}

    def verify(self, **overrides):
        return self.tools["research_verify_result"].invoke(self.capture(**overrides))

    def finalize(self):
        self.state.complete_source("Discovery", SourceStatus.COMPLETED)
        return self.tools["research_finalize"].invoke({"result_id": self.result.result_id})


class QuoteVerificationTests(unittest.TestCase):
    def test_price_change_replaces_discovery_and_preserves_history_in_every_category(self):
        for category in SCOPES:
            with self.subTest(category=category):
                f = ResearchFixture(category)
                self.assertIn("VERIFIED RESULT", f.verify())
                self.assertEqual(get_public_total(f.result, strict=True), 6000)
                self.assertEqual(f.result.price_history[0]["price"], 4500)
                self.assertEqual(f.result.price_history[-1]["price"], 6000)

    def test_old_discovery_price_cannot_replace_fresh_price(self):
        f = ResearchFixture()
        payload = f.capture()
        payload["quote"]["price"] = 4500
        response = f.tools["research_verify_result"].invoke(payload)
        self.assertIn("Observed amount is", response)
        self.assertFalse(f.result.verified)

    def test_missing_numeric_amount_is_rejected(self):
        f = ResearchFixture()
        payload = f.capture()
        payload["quote"]["price_amount_texts"] = {"price": "4500.00"}
        self.assertIn("does not occur", f.tools["research_verify_result"].invoke(payload))

    def test_price_outside_selected_offer_is_rejected(self):
        f = ResearchFixture()
        payload = f.capture()
        current = f.store.get(payload["observation_id"])
        page = '- generic [ref=page]:\n' + '\n'.join('  ' + line for line in current.page_text.splitlines())
        page += '\n  - article [ref=other]:\n    - generic [ref=otherprice]: Price: 4500.00 TRY'
        obs = f.store.capture(f.result.offer_url, page)
        payload["observation_id"] = obs.observation_id
        payload["quote"].update(price=4500, price_evidence='- generic [ref=otherprice]: Price: 4500.00 TRY',
                                price_amount_texts={"price": "4500.00"})
        self.assertIn("selected offer subtree", f.tools["research_verify_result"].invoke(payload))

    def test_linked_price_for_other_seller_cannot_verify_current_seller(self):
        f = ResearchFixture()
        f.result.offer_url += "?sellerid=one"
        text, quote = snapshot_and_quote()
        text = text.replace('- generic [ref=price]: Price: 6000.00 TRY',
                            '- link "6000.00 TRY" [ref=price]:\n    - /url: /offer?sellerid=two')
        quote["price_evidence"] = '- link "6000.00 TRY" [ref=price]:'
        obs = f.store.capture(f.result.offer_url, text)
        response = f.tools["research_verify_result"].invoke(dict(result_id=f.result.result_id,
                                                               observation_id=obs.observation_id, quote=quote))
        self.assertIn("different offer", response)
        self.assertFalse(f.result.verified)

    def test_changed_seller_is_a_different_offer(self):
        f = ResearchFixture()
        f.result.seller = "Another Provider"
        self.assertIn("seller/provider changed", f.verify())

    def test_unit_prices_are_not_comparable_totals_for_any_category(self):
        for category in SCOPES:
            with self.subTest(category=category):
                f = ResearchFixture(category)
                self.assertIn("VERIFIED RESULT", f.verify(price_scope="unit", scope_evidence=None))
                self.assertIsNone(get_public_total(f.result, strict=True))
                self.assertIn("BLOCKED", f.finalize())

    def test_unknown_fees_remain_unknown(self):
        f = ResearchFixture("hotel")
        self.assertIn("VERIFIED RESULT", f.verify(fees_included=False, fees_evidence=None))
        self.assertIsNone(get_public_total(f.result, strict=True))

    def test_generic_mandatory_fees_work_for_every_category(self):
        for category in SCOPES:
            with self.subTest(category=category):
                f = ResearchFixture(category)
                response = f.verify(fees_included=False, mandatory_fees=120,
                                    fees_evidence="Mandatory fees: 120.00 TRY", fee_amount_text="120.00")
                self.assertIn("VERIFIED RESULT", response)
                self.assertEqual(get_public_total(f.result, strict=True), 6120)

    def test_travel_does_not_use_fake_zero_shipping(self):
        f = ResearchFixture("flight")
        self.assertIn("not shipping_cost", f.verify(fees_included=False, fees_evidence=None,
                                                     shipping_cost=0, shipping_evidence="Free shipping"))

    def test_condition_requires_evidence(self):
        f = ResearchFixture()
        self.assertIn("Price condition evidence", f.verify(price_condition="Members only"))

    def test_expired_and_invalidated_observations_are_rejected(self):
        f = ResearchFixture()
        payload = f.capture()
        obs = f.store.get(payload["observation_id"])
        f.store._observations[obs.observation_id] = replace(obs, captured_at=datetime.now(timezone.utc) - timedelta(minutes=6))
        self.assertIn("expired", f.tools["research_verify_result"].invoke(payload))
        payload = f.capture()
        f.store.invalidate_current()
        self.assertIn("no longer current", f.tools["research_verify_result"].invoke(payload))

    def test_failed_recheck_invalidates_previous_verification(self):
        f = ResearchFixture()
        f.verify()
        payload = f.capture()
        payload["quote"]["price"] = 4500
        f.tools["research_verify_result"].invoke(payload)
        self.assertFalse(f.result.verified)
        self.assertEqual(f.result.verification_status, VerificationStatus.PENDING)

    def test_final_page_requires_a_new_snapshot(self):
        f = ResearchFixture()
        payload = f.capture()
        f.tools["research_verify_result"].invoke(payload)
        self.assertIn("APPROVED", f.finalize())
        self.assertIn("new browser_snapshot", f.tools["research_confirm_final_page"].invoke(payload))
        self.assertFalse(f.state.is_ready_to_return())
        self.assertIn("CONFIRMED", f.tools["research_confirm_final_page"].invoke(f.capture()))
        self.assertTrue(f.state.is_ready_to_return())

    def test_price_change_on_final_page_reopens_ranking(self):
        for category in SCOPES:
            with self.subTest(category=category):
                f = ResearchFixture(category)
                f.verify()
                f.finalize()
                response = f.tools["research_confirm_final_page"].invoke(f.capture(price=7000))
                self.assertIn("FINAL PAGE CHANGED", response)
                self.assertEqual(get_public_total(f.result, strict=True), 7000)
                self.assertFalse(f.state.is_finalized())


def priced_result(price, currency="TRY", **overrides):
    values = dict(title="Matching offer", source="Discovery", price=price, currency=currency,
                  verified=True, verification_status=VerificationStatus.VERIFIED,
                  price_scope="total", fees_included=True)
    values.update(overrides)
    return ComparisonResult(**values)


class RankingAndCompletionTests(unittest.TestCase):
    def test_fresh_merchant_price_changes_winner_in_every_category(self):
        for category in SCOPES:
            with self.subTest(category=category):
                f = ResearchFixture(category)
                f.state.add_result(priced_result(5200))
                f.verify()
                self.assertEqual(find_best_overall(f.state, verified_only=True).price, 5200)

    def test_mixed_currencies_are_grouped_not_compared(self):
        f = ResearchFixture()
        f.state.results.clear()
        f.state.add_result(priced_result(1000, "USD"))
        f.state.add_result(priced_result(2000, "TRY"))
        self.assertIsNone(find_best_overall(f.state, verified_only=True))
        report = f.tools["research_rankings"].invoke({"verified_only": True})
        self.assertIn("Currency: USD", report)
        self.assertIn("Currency: TRY", report)
        self.assertIn("Overall public winner: None", report)

    def test_unknown_currency_cannot_create_winner(self):
        state = ComparisonState(query="cheapest")
        state.add_result(priced_result(1000, None))
        self.assertIsNone(find_best_overall(state, verified_only=True))
        self.assertEqual(normalize_currency("tl"), "TRY")

    def test_conditional_offer_is_not_automatically_eligible(self):
        state = ComparisonState(query="cheapest")
        state.add_result(priced_result(100))
        state.add_result(priced_result(80, price_condition="Paid membership"))
        self.assertEqual(find_best_overall(state, verified_only=True).price, 100)
        self.assertEqual(find_best_conditional(state, verified_only=True).price, 80)

    def test_rankings_and_finalization_agree_on_unknown_costs(self):
        f = ResearchFixture()
        f.state.results.clear()
        f.state.add_result(priced_result(100, fees_included=False))
        f.state.add_result(priced_result(120))
        f.state.complete_source("Discovery", SourceStatus.COMPLETED)
        best = find_best_overall(f.state, verified_only=True)
        self.assertEqual(best.price, 120)
        self.assertIn("APPROVED", f.tools["research_finalize"].invoke({"result_id": best.result_id}))

    def test_blocked_cheaper_offer_does_not_prevent_source_completion(self):
        f = ResearchFixture()
        f.result.verification_status = VerificationStatus.BLOCKED
        f.state.add_result(priced_result(6000))
        self.assertEqual(get_unverified_source_winners(f.state, "Discovery"), [])
        f.state.start_source("Discovery")
        self.assertIn("FINISHED", f.tools["research_complete_source"].invoke({
            "source": "Discovery", "outcome": "completed", "coverage_summary": "One offer verified, other blocked.",
        }))

    def test_all_empty_sources_are_a_finished_research_outcome(self):
        state = ComparisonState(query="cheapest", planned_sources=["A", "B"])
        for source in state.planned_sources:
            state.complete_source(source, SourceStatus.NO_RESULTS)
        self.assertTrue(state.is_ready_to_return())
        self.assertFalse(state.is_finalized())

    def test_unknown_costs_can_finish_with_an_explanation(self):
        f = ResearchFixture("hotel")
        f.verify(fees_included=False, fees_evidence=None)
        f.state.complete_source("Discovery", SourceStatus.COMPLETED)
        response = f.tools["research_finish_without_winner"].invoke({})
        self.assertIn("FINISHED WITHOUT WINNER", response)
        self.assertTrue(f.state.is_ready_to_return())
        self.assertFalse(f.state.final_page_verified)

    def test_pending_offer_prevents_finishing_without_winner(self):
        f = ResearchFixture()
        f.state.complete_source("Discovery", SourceStatus.BLOCKED)
        self.assertFalse(f.state.is_ready_to_return())
        self.assertIn("FINISH BLOCKED", f.tools["research_finish_without_winner"].invoke({}))

    def test_new_offer_reopens_finished_research(self):
        f = ResearchFixture()
        f.result.verification_status = VerificationStatus.BLOCKED
        f.state.complete_source("Discovery", SourceStatus.BLOCKED)
        self.assertTrue(f.state.is_ready_to_return())
        f.state.add_result(ComparisonResult(title="New", source="Discovery"))
        self.assertFalse(f.state.is_ready_to_return())

    def test_nan_and_infinity_are_rejected(self):
        for value in (float("nan"), float("inf"), -1):
            self.assertIsNotNone(validate_money_values(price=value))
            with self.assertRaises(ValueError):
                _, quote = snapshot_and_quote()
                quote["price"] = value
                OfferQuote.model_validate(quote)


class UrlIdentityTests(unittest.TestCase):
    def test_same_seller_is_not_same_product(self):
        self.assertFalse(urls_match("https://x.example/a?sellerid=42", "https://x.example/b?sellerid=42"))

    def test_missing_identity_parameter_is_not_a_match(self):
        self.assertFalse(urls_match("https://x.example/a?sellerid=42", "https://x.example/a"))

    def test_changed_variant_or_booking_dates_are_not_a_match(self):
        for field in ("renk", "variant", "checkin", "adults"):
            self.assertFalse(urls_match(f"https://x.example/a?{field}=one", f"https://x.example/a?{field}=two"))

    def test_tracking_and_trailing_slash_are_ignored(self):
        self.assertTrue(urls_match("https://www.x.example/a?sku=42&utm_source=ad", "https://x.example/a/?sku=42"))

    def test_strong_product_identifier_allows_slug_change(self):
        self.assertTrue(urls_match("https://x.example/a?sku=42", "https://x.example/b?sku=42"))

    def test_relative_urls_are_not_exact_offer_urls(self):
        self.assertFalse(urls_match("/a", "/a"))


class PlanningTests(unittest.TestCase):
    def test_research_wording_starts_structured_comparison(self):
        for prompt in (
            "Logitech mouse fiyatlarını araştır",
            "İstanbul için otel araştır",
            "Research flight options to Berlin",
            "Araç kiralama seçeneklerini araştır",
        ):
            with self.subTest(prompt=prompt):
                self.assertEqual(classify_task(prompt), TaskType.COMPARISON)

    def test_general_research_has_a_nonempty_source_plan(self):
        self.assertEqual(
            plan_sources("Research language courses", category=ResearchCategory.GENERAL),
            ["Web Search"],
        )


class BrowserEvidenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_browser_actions_invalidate_old_evidence_and_serialize(self):
        from core.tools.browser import BrowserManager
        browser = BrowserManager()
        browser.observations.capture("https://x.example", "page")
        events = []

        async def handler(request):
            events.append(("start", request.name))
            self.assertIsNone(browser.observations.current_observation_id)
            await asyncio.sleep(0)
            events.append(("end", request.name))
            return "ok"

        await asyncio.gather(*(
            browser._track_browser_action(SimpleNamespace(name=name), handler)
            for name in ("navigate", "click")
        ))
        self.assertEqual(events, [("start", "navigate"), ("end", "navigate"), ("start", "click"), ("end", "click")])

    def test_archived_observation_can_be_read_without_becoming_current(self):
        from core.security.policy import (
            SecurityAction,
            evaluate_tool_call,
        )

        f = ResearchFixture()

        payload = f.capture()
        observation_id = payload["observation_id"]

        # Simulate moving away from the page.
        f.store.invalidate_current()

        self.assertIsNone(
            f.store.current_observation_id
        )

        response = f.tools[
            "research_read_observation"
        ].invoke(
            {
                "observation_id": observation_id,
                "offer_ref": "offer",
            }
        )

        self.assertIn(
            "ARCHIVED BROWSER OBSERVATION",
            response,
        )
        self.assertIn(
            observation_id,
            response,
        )
        self.assertIn(
            "Price: 6000.00 TRY",
            response,
        )

        # Reading archived evidence must not make it current again.
        self.assertIsNone(
            f.store.current_observation_id
        )

        with self.assertRaises(ValueError):
            f.store.require_current(
                observation_id
            )

        decision = evaluate_tool_call(
            "research_read_observation",
            {
                "observation_id": observation_id,
            },
        )

        self.assertEqual(
            decision.action,
            SecurityAction.ALLOW,
        )


class AgentReportTests(unittest.IsolatedAsyncioTestCase):
    def test_progress_signature_tracks_all_planned_sources_and_offer_changes(self):
        from core.agent import JarvisAgent
        f = ResearchFixture()
        agent = object.__new__(JarvisAgent)
        agent.current_comparison_state = f.state
        before = agent._research_progress_signature()
        f.state.start_source("Discovery")
        after_source_start = agent._research_progress_signature()
        self.assertNotEqual(before, after_source_start)
        f.result.price = 6100
        self.assertNotEqual(after_source_start, agent._research_progress_signature())

    async def test_report_uses_unbound_model_and_records_every_offer_and_price_change(self):
        from core.agent import JarvisAgent
        from langchain_core.messages import AIMessage
        f = ResearchFixture("hotel")
        f.verify()
        f.state.planned_sources.append("Blocked source")
        from core.research.comparison_state import SourceResearchState
        f.state.source_states["Blocked source"] = SourceResearchState(source="Blocked source", status=SourceStatus.BLOCKED)
        report_model = SimpleNamespace(ainvoke=AsyncMock(return_value=AIMessage(content="Comparison report")))
        agent = object.__new__(JarvisAgent)
        agent.current_comparison_state = f.state
        agent.observation_store = f.store
        agent.llm = SimpleNamespace(get_model=lambda: report_model, get_fallback_model=lambda: report_model)
        agent.agent = SimpleNamespace(ainvoke=AsyncMock(), aupdate_state=AsyncMock())
        answer = await agent._generate_research_report("Compare hotel prices", {})
        self.assertEqual(answer, "Comparison report")
        agent.agent.ainvoke.assert_not_called()
        agent.agent.aupdate_state.assert_awaited_once()
        messages = report_model.ainvoke.call_args.args[0]
        for expected in ("Discovery", "Blocked source", "4500", "6000", "price_history"):
            self.assertIn(expected, messages[1]["content"])

    async def test_browser_navigation_after_confirmation_clears_final_page_claim(self):
        from core.agent import JarvisAgent
        f = ResearchFixture()
        f.verify()
        f.finalize()
        f.tools["research_confirm_final_page"].invoke(f.capture())
        self.assertTrue(f.state.final_page_verified)
        agent = object.__new__(JarvisAgent)
        agent.current_comparison_state = f.state
        agent.observation_store = f.store
        f.store.invalidate_current()
        context = agent._build_final_research_context()
        self.assertFalse(f.state.final_page_verified)
        self.assertIn("FINAL PAGE VERIFIED: False", context)


class CompletionGuardTests(unittest.IsolatedAsyncioTestCase):
    async def test_ready_research_skips_model_but_report_and_normal_chat_still_use_it(self):
        from core.agent import JarvisAgent
        from core.context import RequestContext

        f = ResearchFixture()

        f.verify()
        f.finalize()

        response = f.tools[
            "research_confirm_final_page"
        ].invoke(f.capture())

        self.assertIn("CONFIRMED", response)
        self.assertTrue(f.state.is_ready_to_return())

        model = CountingChatModel()

        llm = SimpleNamespace(
            get_model=lambda: model,
            get_fallback_model=lambda: model,
        )

        agent = JarvisAgent(
            llm,
            observation_store=f.store,
        )

        agent.current_comparison_state = f.state

        config = {
            "configurable": {
                "thread_id": "completion-guard-test",
            }
        }

        # Ready research must end before another research model call.
        await agent.agent.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "Compare prices",
                    }
                ]
            },
            config=config,
            context=RequestContext(
                user_message="Compare prices",
                research_active=True,
            ),
        )

        self.assertEqual(model.call_count, 0)

        # Final report must still use the model exactly once.
        report = await agent._generate_research_report(
            "Compare prices",
            config,
        )

        self.assertEqual(report, "model response")
        self.assertEqual(model.call_count, 1)

        # A later normal chat request must not be blocked.
        await agent.agent.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "Merhaba",
                    }
                ]
            },
            config=config,
            context=RequestContext(
                user_message="Merhaba",
                research_active=False,
            ),
        )

        self.assertEqual(model.call_count, 2)


if __name__ == "__main__":
    unittest.main()
