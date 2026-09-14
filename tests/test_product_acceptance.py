"""Acceptance regressions from the audit, including an archived real page.

The Koctas fixture is an excerpt of page-2026-09-13T10-35-03-968Z.yml.
It is historical test data, never evidence of a current price.
"""

from pathlib import Path
import unittest

from core.research.comparison_state import ComparisonState, ComparisonResult
from core.research.evidence import ObservationStore
from core.research.research_tools import create_research_tools
from core.research.research_manager import product_criteria
from core.research.product_quote import read_amount
from core.research.discovery_evidence import has_discovery_identity
from core.research.report import render_report_table
from core.research.source_planner import plan_sources
from tests.test_research_workflow import ResearchFixture


URL = "https://www.koctas.com.tr/logitech-g-pro-x-superlight-2-hafif-hero-2-sensor-32000-dpi-lightspeed-kablosuz-oyuncu-mouse-siyah/p/5000673826"
PAGE = (Path(__file__).parent / "fixtures/koctas-product-archived.yml").read_text(encoding="utf-8")
SELECTION = dict(offer_ref="f12e83", identity_ref="f12e84", seller_ref="f12e96",
                 seller="GamingGenTR", price_ref="f12e143", currency="TRY",
                 decimal_separator=",", quantity_ref="f12e136", shipping_ref="f12e110")


class ProductAcceptanceTests(unittest.TestCase):
    def setUp(self):
        query = "Logitech Superlight 2 mouse en ucuz fiyatını araştır"
        self.state = ComparisonState(query=query, category="product", target_product="Logitech Superlight 2",
                                     criteria=product_criteria(query), planned_sources=plan_sources(query))
        self.store = ObservationStore()
        self.tools = {t.name: t for t in create_research_tools(lambda: self.state, self.store)}
        self.tools["research_start_source"].invoke({"source": "Google Shopping"})
        observation = self.store.capture("https://www.google.com/search?tbm=shop&q=Logitech+Superlight+2", "Logitech Superlight 2 listing")
        self.tools["research_record_discovery_attempt"].invoke(dict(source="Google Shopping", query="Logitech Superlight 2", observation_id=observation.observation_id))
        response = self.tools["research_add_result"].invoke(dict(title="Logitech Superlight 2", source="Google Shopping",
                      price=4500, currency="TRY", url=observation.page_url, offer_url=URL, observation_id=observation.observation_id))
        self.assertIn("STORED RESULT:", response)

    def verify(self, *, final_check=False, page=PAGE, selection=None):
        observation = self.store.capture(URL, page)
        return self.tools["research_verify_product"].invoke(dict(result_id="result_1", observation_id=observation.observation_id,
                     selection=selection or SELECTION, final_check=final_check))

    def test_archived_real_page_quote_is_copied_and_verified(self):
        self.assertIn("VERIFIED RESULT:", self.verify())
        result = self.state.results[0]
        self.assertEqual(result.public_total, 6989)
        self.assertEqual(result.seller, "GamingGenTR")
        self.assertEqual(result.price_history[0]["price"], 4500)
        self.assertIn("[ref=f12e143]", result.verification_price_evidence)

    def test_alternative_seller_price_cannot_be_borrowed(self):
        response = self.verify(selection={**SELECTION, "price_ref": "f12e176"})
        self.assertIn("different offer containers", response)
        self.assertFalse(self.state.results[0].verified)

    def test_unverified_platform_label_is_resolved_to_actual_merchant(self):
        self.state.results[0].seller = "Koçtaş"
        self.assertIn("VERIFIED RESULT:", self.verify())
        result = self.state.results[0]
        self.assertEqual(result.seller, "GamingGenTR")
        self.assertEqual(result.price_history[0]["seller"], "Koçtaş")
        self.assertEqual(result.details["discovery_seller_label"], "Koçtaş")
        report = render_report_table(self.state, self.state.query)
        self.assertIn("Koçtaş → GamingGenTR", report)

    def test_actual_merchant_and_previously_verified_platform_seller_stay_fixed(self):
        self.state.results[0].seller = "Jetklik"
        self.assertIn("seller/provider changed", self.verify())
        self.state.results[0].seller = "Koçtaş"
        self.state.results[0].price_history = [{"stage":"verified", "seller":"Koçtaş", "price":4500}]
        self.assertIn("seller/provider changed", self.verify())

    def test_wrong_product_price_in_a_sibling_card_is_rejected(self):
        f = ResearchFixture()
        payload = f.capture()
        original = f.store.get(payload["observation_id"]).page_text
        page = '- main [ref=root]:\n' + '\n'.join('  ' + line for line in original.splitlines())
        page += '\n  - article [ref=other]:\n    - heading [ref=otherid]: Wrong product\n    - generic [ref=otherprice]: 100.00 TRY'
        observation = f.store.capture(f.result.offer_url, page)
        payload["observation_id"] = observation.observation_id
        payload["quote"].update(offer_ref="root", price=100, price_amount_texts={"price":"100.00"}, price_evidence='- generic [ref=otherprice]: 100.00 TRY')
        self.assertIn("different offer containers", f.tools["research_verify_result"].invoke(payload))

    def test_full_requested_quantity_is_not_assumed(self):
        self.state.criteria = product_criteria("10 adet Logitech mouse")
        self.assertIn("quantity", self.verify())
        self.assertFalse(self.state.results[0].verified)

    def test_unknown_shipping_never_becomes_zero(self):
        self.assertIn("VERIFIED RESULT", self.verify(selection={**SELECTION, "shipping_ref": None}))
        self.assertIsNone(self.state.results[0].public_total)

    def test_number_format_and_currency_are_not_guessed(self):
        self.assertEqual(read_amount('- generic [ref=e123]: 6.989 TL', ','), ('6.989', 6989.0))
        with self.assertRaises(ValueError):
            read_amount('- generic [ref=e123]: 6.989 TL', '.')
        with self.assertRaises(ValueError):
            read_amount('- generic [ref=e123]: 6.989 TL', ',', '6.989 TL')

    def test_refs_outside_selected_scope_return_an_actionable_correction(self):
        response = self.verify(selection={**SELECTION, "offer_ref": "f12e142"})
        self.assertIn("outside offer_ref", response)
        self.assertIn("Common container: f12e83", response)
        self.assertNotIn("Unknown snapshot reference", response)
        self.assertFalse(self.state.results[0].verified)

    def test_unrelated_text_cannot_prove_all_fees_included(self):
        f = ResearchFixture()
        self.assertIn("Inclusive fees require", f.verify(fees_evidence="Example Provider"))

    def test_unobserved_or_repeated_searches_cannot_close_a_source(self):
        self.tools["research_start_source"].invoke({"source": "Itopya"})
        self.assertIn("REJECTED", self.tools["research_record_discovery_attempt"].invoke(dict(source="Itopya", query="one")))
        obs = self.store.capture("https://www.itopya.com/arama/", "No items")
        self.tools["research_record_discovery_attempt"].invoke(dict(source="Itopya", query="one", observation_id=obs.observation_id))
        obs2 = self.store.capture(obs.page_url, obs.page_text)
        self.assertIn("NOT COUNTED", self.tools["research_record_discovery_attempt"].invoke(dict(source="Itopya", query="two", observation_id=obs2.observation_id)))
        self.assertIn("BLOCKED", self.tools["research_complete_source"].invoke(dict(source="Itopya", outcome="no_results", coverage_summary="three searches")))
        self.assertIn("BLOCKED", self.tools["research_complete_source"].invoke(dict(source="Itopya", outcome="blocked", coverage_summary="access failed")))

    def test_same_seven_sources_can_finish_with_verified_offer_and_links(self):
        self.assertEqual(len(self.state.planned_sources), 7)
        self.assertIn("VERIFIED RESULT:", self.verify())
        self.tools["research_complete_source"].invoke(dict(source="Google Shopping", outcome="completed", coverage_summary="Offer verified"))
        domains = dict(Akakce="akakce.com", **{"Vatan Computer":"vatanbilgisayar.com", "Itopya":"itopya.com", "Hepsiburada":"hepsiburada.com", "Trendyol":"trendyol.com", "Ciceksepeti":"ciceksepeti.com"})
        for source in self.state.planned_sources[1:]:
            self.tools["research_start_source"].invoke({"source":source})
            observation = self.store.capture("https://"+domains[source]+"/", "Access denied", kind="error")
            result = self.tools["research_complete_source"].invoke(dict(source=source, outcome="blocked", coverage_summary="Access denied", observation_id=observation.observation_id, observed_evidence="Access denied"))
            self.assertIn("FINISHED", result)
        self.assertIn("APPROVED", self.tools["research_finalize"].invoke({"result_id":"result_1"}))
        self.assertIn("CONFIRMED", self.verify(final_check=True))
        self.assertTrue(self.state.is_ready_to_return())
        report = render_report_table(self.state, self.state.query)
        for source in self.state.planned_sources:
            self.assertIn(source, report)
        self.assertIn(URL, report)
        self.assertIn("GamingGenTR", report)
        self.assertIn("verified", report)
        self.assertIn("4,500.00", report)
        self.assertIn("6,989.00", report)
        self.store.invalidate_current()
        self.assertIn("no longer current", self.tools["research_verify_product"].invoke(dict(result_id="result_1", observation_id=self.state.final_page_observation_id, selection=SELECTION)))

    def test_final_price_change_reopens_winner(self):
        self.verify()
        for source in self.state.planned_sources:
            from core.research.comparison_state import SourceStatus
            self.state.complete_source(source, SourceStatus.BLOCKED)
        self.tools["research_finalize"].invoke({"result_id":"result_1"})
        self.assertIn("FINAL PAGE CHANGED", self.verify(final_check=True, page=PAGE.replace('6.989 TL', '7.999 TL')))
        self.assertFalse(self.state.is_finalized())
        self.assertEqual(self.state.results[0].public_total, 7999)

    def test_recommendation_edition_does_not_reject_the_actual_product(self):
        page = '''- main [ref=main]:
  - heading "Logitech G PRO X SUPERLIGHT 2 Siyah Mouse" [ref=title]
  - generic [ref=description]:
    - img "Logitech G PRO X SUPERLIGHT 2 DEX" [ref=img]
  - link "Logitech G PRO X SUPERLIGHT 2 SE" [ref=other]'''
        self.assertTrue(has_discovery_identity(page, "Logitech Superlight 2", "Logitech G PRO X SUPERLIGHT 2 Siyah Mouse"))
        self.assertFalse(has_discovery_identity(page, "Logitech Superlight 2", "Logitech Superlight 2 Beyaz"))
        self.assertFalse(has_discovery_identity('- heading "Logitech Superlight 2 DEX" [ref=e1]', "Logitech Superlight 2", "Logitech Superlight 2"))

    def test_generic_and_yaml_quoted_shopping_titles_are_discovery_evidence(self):
        for page in ('- generic [ref=e1]: Logitech G Pro X Superlight 2',
                     '''- 'button "Logitech G Pro X Superlight 2. Fiyat: 6.989 TL" [ref=e1]' '''):
            self.assertTrue(has_discovery_identity(page, "Logitech Superlight 2", "Logitech G Pro X Superlight 2"))
        split_cards = '''- generic [ref=root]:
  - generic [ref=e1]: Logitech Superlight
  - generic [ref=e2]: Unrelated product 2'''
        self.assertFalse(has_discovery_identity(split_cards, "Logitech Superlight 2", "Logitech Superlight 2"))

    def test_access_failures_never_count_as_empty_searches(self):
        self.tools["research_start_source"].invoke({"source": "Akakce"})
        for i, text in enumerate(("reCAPTCHA", "Güvenlik doğrulaması yapılıyor", "Sorry, you have been blocked")):
            obs = self.store.capture(f"https://www.akakce.com/?q={i}", f'- heading "{text}" [ref=e1]')
            response = self.tools["research_record_discovery_attempt"].invoke(dict(source="Akakce", query=str(i), observation_id=obs.observation_id))
            self.assertIn("NOT COUNTED", response)
        self.assertIn("BLOCKED", self.tools["research_complete_source"].invoke(dict(source="Akakce", outcome="no_results", coverage_summary="three attempts")))
        self.assertIn("FINISHED", self.tools["research_complete_source"].invoke(dict(source="Akakce", outcome="blocked", coverage_summary="Access challenge", observation_id=obs.observation_id, observed_evidence=text)))
        self.assertEqual(self.state.get_source_state("Akakce").status.value, "blocked")

    def test_matching_discovery_cannot_be_reported_as_no_inventory(self):
        self.tools["research_start_source"].invoke({"source": "Itopya"})
        obs = self.store.capture("https://www.itopya.com/ara?bul=superlight", '- link "Logitech Superlight 2 Mouse" [ref=e1]')
        self.tools["research_record_discovery_attempt"].invoke(dict(source="Itopya", query="superlight", observation_id=obs.observation_id))
        response = self.tools["research_complete_source"].invoke(dict(source="Itopya", outcome="no_results", coverage_summary="could not store"))
        self.assertIn("matching product", response)

    def test_three_real_empty_searches_can_close_as_no_results(self):
        self.tools["research_start_source"].invoke({"source": "Vatan Computer"})
        for query in ("Logitech Superlight 2", "Superlight 2", "superlight"):
            obs = self.store.capture(f"https://www.vatanbilgisayar.com/arama/{query}", '- heading "Arama sonuçları" [ref=e1]\n- paragraph [ref=e2]: 0 ürün bulundu')
            self.tools["research_record_discovery_attempt"].invoke(dict(source="Vatan Computer", query=query, observation_id=obs.observation_id))
        self.assertIn("FINISHED", self.tools["research_complete_source"].invoke(dict(source="Vatan Computer", outcome="no_results", coverage_summary="Three real searches with no items")))
