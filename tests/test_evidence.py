import unittest

from core.research.evidence import get_interactive_snapshot


class InteractiveSnapshotTests(unittest.TestCase):

    def test_keeps_interactive_controls(self):
        page_text = """
- heading "Book a flight" [ref=e1]
- textbox "From" [ref=e2]
- textbox "To" [ref=e3]
- button "Departure date" [ref=e4]
- button "Search flights" [ref=e5]
- paragraph "Cheap flights are available" [ref=e6]
""".strip()

        result = get_interactive_snapshot(page_text)

        # Interactive controls should stay
        self.assertIn(
            'textbox "From" [ref=e2]',
            result,
        )
        self.assertIn(
            'textbox "To" [ref=e3]',
            result,
        )
        self.assertIn(
            'button "Departure date" [ref=e4]',
            result,
        )
        self.assertIn(
            'button "Search flights" [ref=e5]',
            result,
        )

        # Non-interactive content should not become its own block
        self.assertNotIn(
            'paragraph "Cheap flights are available" [ref=e6]',
            result,
        )


    def test_skips_controls_without_ref(self):
        page_text = """
- textbox "From"
- textbox "To" [ref=e2]
- button "Search"
""".strip()

        result = get_interactive_snapshot(page_text)

        # Only controls with a semantic ref can be used
        self.assertIn(
            'textbox "To" [ref=e2]',
            result,
        )

        self.assertNotIn(
            'textbox "From"',
            result,
        )

        self.assertNotIn(
            'button "Search"',
            result,
        )


    def test_keeps_child_nodes(self):
        page_text = """
- combobox "From" [ref=e1]
  - text: Istanbul
  - option "Istanbul Airport" [ref=e2]
- combobox "To" [ref=e3]
""".strip()

        result = get_interactive_snapshot(page_text)

        # The control subtree should keep useful child data
        self.assertIn(
            'combobox "From" [ref=e1]',
            result,
        )

        self.assertIn(
            "text: Istanbul",
            result,
        )

        self.assertIn(
            'option "Istanbul Airport" [ref=e2]',
            result,
        )


    def test_keeps_nearby_label_text(self):
        page_text = """
- text: Departure city
- generic
- textbox [ref=e1]
""".strip()

        result = get_interactive_snapshot(page_text)

        # Nearby text can explain what a control means
        self.assertIn(
            "Departure city",
            result,
        )

        self.assertIn(
            "textbox [ref=e1]",
            result,
        )


    def test_returns_empty_when_no_controls_exist(self):
        page_text = """
- heading "Pegasus"
- paragraph "Welcome to the website"
- generic
""".strip()

        result = get_interactive_snapshot(page_text)

        # No interactive controls means no snapshot
        self.assertEqual(
            result,
            "",
        )


    def test_respects_max_controls(self):
        page_text = """
- textbox "From" [ref=e1]
- textbox "To" [ref=e2]
- button "Date" [ref=e3]
- button "Search" [ref=e4]
""".strip()

        result = get_interactive_snapshot(
            page_text,
            max_controls=2,
        )

        # Only the first two controls should be included
        self.assertIn(
            'textbox "From" [ref=e1]',
            result,
        )

        self.assertIn(
            'textbox "To" [ref=e2]',
            result,
        )

        self.assertNotIn(
            'button "Date" [ref=e3]',
            result,
        )

        self.assertNotIn(
            'button "Search" [ref=e4]',
            result,
        )


    def test_respects_max_chars(self):
        page_text = """
- textbox "From Istanbul Airport" [ref=e1]
- textbox "To Izmir Adnan Menderes Airport" [ref=e2]
- button "Search flights for selected route" [ref=e3]
""".strip()

        result = get_interactive_snapshot(
            page_text,
            max_chars=70,
        )

        # The first block may be added, but later blocks
        # must stop when the size limit is reached
        self.assertIn(
            'textbox "From Istanbul Airport" [ref=e1]',
            result,
        )

        self.assertNotIn(
            'button "Search flights for selected route" [ref=e3]',
            result,
        )


    def test_supports_flight_form_controls(self):
        page_text = """
- heading "Flight Search" [ref=e1]
- combobox "From" [ref=e2]
- combobox "To" [ref=e3]
- button "Departure date" [ref=e4]
- gridcell "15" [ref=e5]
- spinbutton "Passengers" [ref=e6]
- checkbox "Direct flights only" [ref=e7]
- button "Search flights" [ref=e8]
""".strip()

        result = get_interactive_snapshot(page_text)

        # Flight form controls should be visible to the agent
        self.assertIn(
            'combobox "From" [ref=e2]',
            result,
        )

        self.assertIn(
            'combobox "To" [ref=e3]',
            result,
        )

        self.assertIn(
            'button "Departure date" [ref=e4]',
            result,
        )

        self.assertIn(
            'gridcell "15" [ref=e5]',
            result,
        )

        self.assertIn(
            'spinbutton "Passengers" [ref=e6]',
            result,
        )

        self.assertIn(
            'checkbox "Direct flights only" [ref=e7]',
            result,
        )

        self.assertIn(
            'button "Search flights" [ref=e8]',
            result,
        )


    def test_keeps_link_autocomplete_options(self):
        page_text = """
- textbox "Nereden" [ref=e1]
- list [ref=e2]
  - link "İstanbul Tümü" [ref=e3]
  - link "İstanbul Sabiha Gökçen" [ref=e4]
  - link "İstanbul Havalimanı" [ref=e5]
- textbox "Nereye" [ref=e6]
""".strip()

        result = get_interactive_snapshot(page_text)

        # Autocomplete links must stay visible to the agent
        self.assertIn(
            'link "İstanbul Tümü" [ref=e3]',
            result,
        )

        self.assertIn(
            'link "İstanbul Sabiha Gökçen" [ref=e4]',
            result,
        )

        self.assertIn(
            'link "İstanbul Havalimanı" [ref=e5]',
            result,
        )


    def test_default_limit_keeps_controls_after_first_twenty(self):
        controls = [
            f'- button "Control {index}" [ref=e{index}]'
            for index in range(1, 26)
        ]

        page_text = "\n".join(controls)

        result = get_interactive_snapshot(page_text)

        # The default limit should no longer stop at 20 controls
        self.assertIn(
            'button "Control 20" [ref=e20]',
            result,
        )

        self.assertIn(
            'button "Control 21" [ref=e21]',
            result,
        )

        self.assertIn(
            'button "Control 25" [ref=e25]',
            result,
        )


if __name__ == "__main__":
    unittest.main()