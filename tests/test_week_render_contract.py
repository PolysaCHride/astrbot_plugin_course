"""Regression checks for the weekly schedule render-size contract."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
MAIN = (ROOT / "main.py").read_text(encoding="utf-8")
TEMPLATES = (ROOT / "render_templates.py").read_text(encoding="utf-8")


class WeekRenderContractTests(unittest.TestCase):
    def test_both_week_commands_use_single_template_width(self):
        self.assertIn("WEEK_PAGE_WIDTH = 480", TEMPLATES)
        self.assertEqual(MAIN.count('"page_width": WEEK_PAGE_WIDTH'), 2)
        self.assertNotIn('"page_width": 1280', MAIN)

    def test_template_width_and_grid_contract(self):
        week = TEMPLATES.split("WEEK_TMPL =", 1)[1]
        self.assertIn('width={{ page_width }}', week)
        self.assertIn('width: {{ page_width }}px;', week)
        self.assertIn("grid-template-columns: 1fr 1fr", week)
        self.assertIn("grid-column: span 2", week)
        self.assertNotRegex(week, r"(?:width=|width:\s*)480(?:px)?")


if __name__ == "__main__":
    unittest.main()
