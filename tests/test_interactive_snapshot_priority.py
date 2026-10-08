import unittest

from core.research.evidence import get_interactive_snapshot


class InteractiveSnapshotPriorityTests(unittest.TestCase):

    def test_confirmation_button_survives_large_calendar(self):
        # Create a calendar with many date buttons.
        calendar_buttons = [
            f'- button "Day {day}" [ref=e{day}]'
            for day in range(1, 141)
        ]

        # Add the confirmation button at the end.
        calendar_buttons.append(
            '- button "TAMAM" [ref=e999]'
        )

        page_text = "\n".join(calendar_buttons)

        # Build the compact interactive snapshot.
        result = get_interactive_snapshot(page_text)

        # Important confirmation controls must remain visible.
        self.assertIn(
            'button "TAMAM" [ref=e999]',
            result,
        )

    def test_normal_controls_remain_visible(self):
        # Normal forms must continue working.
        page_text = (
            '- textbox "Nereden" [ref=e1]\n'
            '- textbox "Nereye" [ref=e2]\n'
            '- button "UCUZ UÇUŞ ARA" [ref=e3]'
        )

        result = get_interactive_snapshot(page_text)

        self.assertIn('ref=e1', result)
        self.assertIn('ref=e2', result)
        self.assertIn('ref=e3', result)


if __name__ == "__main__":
    unittest.main()