import unittest
from types import SimpleNamespace

from core.research.comparison_state import ComparisonState
from core.research.evidence import ObservationStore
from core.research.research_manager import (
    create_comparison_state,
    extract_flight_criteria_semantically,
)
from core.research.research_tools import create_research_tools
from core.research.task_classifier import (
    TaskType,
    classify_task,
)


class FakeModel:
    def __init__(self, content: str):
        self.content = content

    async def ainvoke(self, prompt, config=None):
        return SimpleNamespace(content=self.content)


class FakeLLM:
    def __init__(self, content: str):
        self.model = FakeModel(content)

    def get_model(self):
        return self.model


class FlightCriteriaExtractionTests(unittest.IsolatedAsyncioTestCase):

    async def test_extracts_flight_criteria(self):
        # Simulate the structured JSON returned by the model.
        llm = FakeLLM(
            """
            {
                "origin": "İstanbul",
                "destination": "İzmir",
                "departure_date": "15 Ekim",
                "return_date": null,
                "trip_type": "one_way",
                "passengers": 1
            }
            """
        )

        prompt = (
            "15 Ekim'de İstanbul'dan İzmir'e "
            "uçak bileti bul"
        )

        criteria = await extract_flight_criteria_semantically(
            prompt,
            llm,
        )

        self.assertEqual(
            criteria["origin"],
            "İstanbul",
        )

        self.assertEqual(
            criteria["destination"],
            "İzmir",
        )

        self.assertEqual(
            criteria["departure_date"],
            "15 Ekim",
        )

        self.assertIsNone(
            criteria["return_date"],
        )

        self.assertEqual(
            criteria["trip_type"],
            "one_way",
        )

        self.assertEqual(
            criteria["passengers"],
            1,
        )

        self.assertEqual(
            criteria["raw_request"],
            prompt,
        )

    async def test_invalid_json_keeps_raw_request(self):
        # Invalid model output must not crash flight planning.
        llm = FakeLLM(
            "This is not valid JSON."
        )

        prompt = (
            "İstanbul'dan İzmir'e "
            "uçak bileti bul"
        )

        criteria = await extract_flight_criteria_semantically(
            prompt,
            llm,
        )

        self.assertEqual(
            criteria,
            {
                "raw_request": prompt
            },
        )

    async def test_create_comparison_state_keeps_flight_criteria(self):
        # Simulate the structured flight criteria returned by the model.
        llm = FakeLLM(
            """
            {
                "origin": "İstanbul",
                "destination": "İzmir",
                "departure_date": "15 Ekim",
                "return_date": null,
                "trip_type": "one_way",
                "passengers": 1
            }
            """
        )

        prompt = (
            "15 Ekim'de İstanbul'dan İzmir'e "
            "Pegasus'tan uçak bileti bul"
        )

        setup = await create_comparison_state(
            prompt,
            llm,
        )

        self.assertIsNotNone(
            setup.state,
        )

        state = setup.state

        self.assertEqual(
            state.category,
            "flight",
        )

        self.assertEqual(
            state.criteria["origin"],
            "İstanbul",
        )

        self.assertEqual(
            state.criteria["destination"],
            "İzmir",
        )

        self.assertEqual(
            state.criteria["departure_date"],
            "15 Ekim",
        )

        self.assertEqual(
            state.criteria["passengers"],
            1,
        )

        self.assertEqual(
            state.planned_sources,
            ["Pegasus"],
        )

    async def test_source_selection_accepts_turkish_suffix_without_apostrophe(
        self,
    ):
        # Users may write Turkish brand suffixes without an apostrophe.
        llm = FakeLLM(
            """
            {
                "origin": "İstanbul",
                "destination": "İzmir",
                "departure_date": "15 Ekim",
                "return_date": null,
                "trip_type": "one_way",
                "passengers": 1
            }
            """
        )

        prompt = (
            "15 ekimde istanbuldan izmire "
            "pegasustan uçak bileti bul"
        )

        setup = await create_comparison_state(
            prompt,
            llm,
        )

        self.assertIsNotNone(
            setup.state,
        )

        self.assertEqual(
            setup.state.planned_sources,
            ["Pegasus"],
        )


class FlightTaskRoutingTests(unittest.TestCase):

    def test_flight_search_uses_structured_research(self):
        # Flight search requests must use comparison research.
        prompts = [
            (
                "15 ekimde istanbuldan izmire "
                "pegasustan uçak bileti bul"
            ),
            "İstanbul'dan İzmir'e uçuş bul",
            "İstanbul'dan İzmir'e uçuş ara",
            "find a flight from Istanbul to Izmir",
        ]

        for prompt in prompts:
            with self.subTest(prompt=prompt):
                self.assertEqual(
                    classify_task(prompt),
                    TaskType.COMPARISON,
                )

    def test_normal_browser_requests_keep_existing_routing(self):
        # Normal website actions should not become comparison research.
        self.assertEqual(
            classify_task("Pegasus sitesini aç"),
            TaskType.ACTION,
        )

        # General information lookups should stay as lookup tasks.
        self.assertEqual(
            classify_task("Pegasus bagaj hakkı nedir"),
            TaskType.LOOKUP,
        )


class FlightResearchToolTests(unittest.TestCase):

    def setUp(self):
        self.query = (
            "15 Ekim'de İstanbul'dan İzmir'e "
            "Pegasus'tan uçak bileti bul"
        )

        self.state = ComparisonState(
            query=self.query,
            category="flight",
            criteria={
                "origin": "İstanbul",
                "destination": "İzmir",
                "departure_date": "15 Ekim",
                "return_date": None,
                "trip_type": "one_way",
                "passengers": 1,
                "raw_request": self.query,
            },
            planned_sources=[
                "Pegasus",
            ],
        )

        self.store = ObservationStore()

        self.tools = {
            tool.name: tool
            for tool in create_research_tools(
                lambda: self.state,
                self.store,
            )
        }

        start_response = self.tools[
            "research_start_source"
        ].invoke(
            {
                "source": "Pegasus",
            }
        )

        self.assertIn(
            "SOURCE RESEARCH STARTED",
            start_response,
        )

    def capture_flight_page(self):
        # Store fake Pegasus discovery evidence.
        return self.store.capture(
            "https://www.flypgs.com/ucuz-ucak-bileti",
            """
            Istanbul to Izmir

            Pegasus Airlines
            PC 2180

            15 Ekim
            Departure: 10:30
            Arrival: 11:40

            Price: 1.899 TRY
            """,
        )

    def valid_flight_details(self):
        # Return one valid structured flight result.
        return {
            "origin": "İstanbul",
            "destination": "İzmir",
            "departure_date": "15 Ekim",
            "airline": "Pegasus",
            "departure_time": "10:30",
            "arrival_time": "11:40",
            "flight_number": "PC 2180",
        }

    def add_result(
        self,
        *,
        details=None,
    ):
        observation = self.capture_flight_page()

        return self.tools[
            "research_add_result"
        ].invoke(
            {
                "title": (
                    "Pegasus PC 2180 "
                    "İstanbul - İzmir"
                ),
                "source": "Pegasus",
                "price": 1899,
                "currency": "TRY",
                "url": observation.page_url,
                "offer_url": observation.page_url,
                "details": (
                    details
                    if details is not None
                    else self.valid_flight_details()
                ),
                "observation_id": (
                    observation.observation_id
                ),
            }
        )

    def test_valid_flight_result_is_stored(self):
        response = self.add_result()

        self.assertIn(
            "STORED RESULT:",
            response,
        )

        self.assertEqual(
            len(self.state.results),
            1,
        )

        result = self.state.results[0]

        self.assertEqual(
            result.price,
            1899,
        )

        self.assertEqual(
            result.currency,
            "TRY",
        )

        self.assertEqual(
            result.details["origin"],
            "İstanbul",
        )

        self.assertEqual(
            result.details["destination"],
            "İzmir",
        )

        self.assertEqual(
            result.details["airline"],
            "Pegasus",
        )

        self.assertEqual(
            result.details["flight_number"],
            "PC 2180",
        )

    def test_wrong_origin_is_blocked(self):
        details = self.valid_flight_details()

        details["origin"] = "Ankara"

        response = self.add_result(
            details=details,
        )

        self.assertIn(
            "RESULT BLOCKED:",
            response,
        )

        self.assertIn(
            "Flight origin does not match",
            response,
        )

        self.assertEqual(
            len(self.state.results),
            0,
        )

    def test_wrong_destination_is_blocked(self):
        details = self.valid_flight_details()

        details["destination"] = "Antalya"

        response = self.add_result(
            details=details,
        )

        self.assertIn(
            "RESULT BLOCKED:",
            response,
        )

        self.assertIn(
            "Flight destination does not match",
            response,
        )

        self.assertEqual(
            len(self.state.results),
            0,
        )

    def test_missing_required_flight_field_is_blocked(self):
        details = self.valid_flight_details()

        del details["arrival_time"]

        response = self.add_result(
            details=details,
        )

        self.assertIn(
            "RESULT BLOCKED:",
            response,
        )

        self.assertIn(
            "missing required details",
            response,
        )

        self.assertIn(
            "arrival_time",
            response,
        )

        self.assertEqual(
            len(self.state.results),
            0,
        )

    def test_research_status_shows_flight_criteria(self):
        response = self.tools[
            "research_status"
        ].invoke({})

        self.assertIn(
            "Category: flight",
            response,
        )

        self.assertIn(
            "Criteria:",
            response,
        )

        self.assertIn(
            "İstanbul",
            response,
        )

        self.assertIn(
            "İzmir",
            response,
        )

        self.assertIn(
            "15 Ekim",
            response,
        )


if __name__ == "__main__":
    unittest.main()