"""Regression checks for the weekly schedule layout contract."""

import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
MAIN = (ROOT / "main.py").read_text(encoding="utf-8")
TEMPLATES = (ROOT / "render_templates.py").read_text(encoding="utf-8")


class WeekRenderContractTests(unittest.TestCase):
    def test_both_week_commands_keep_template_width_and_shared_options(self):
        tree = ast.parse(MAIN)
        week_calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "html_render" and isinstance(node.args[0], ast.Name)
            and node.args[0].id == "WEEK_TMPL"
        ]
        self.assertEqual(len(week_calls), 2)
        for call in week_calls:
            options = next(keyword for keyword in call.keywords if keyword.arg == "options")
            self.assertIsInstance(options.value, ast.Call)
            self.assertEqual(getattr(options.value.func, "id", None), "_schedule_render_options")
            context = call.args[1]
            page_width = next(
                value for key, value in zip(context.keys, context.values)
                if isinstance(key, ast.Constant) and key.value == "page_width"
            )
            self.assertIsInstance(page_width, ast.Name)
            self.assertEqual(page_width.id, "WEEK_PAGE_WIDTH")

        self.assertIn("WEEK_PAGE_WIDTH = 480", TEMPLATES)
        self.assertNotIn('"page_width": 1280', MAIN)

    def test_template_width_and_grid_contract(self):
        week = TEMPLATES.split("WEEK_TMPL =", 1)[1]
        self.assertIn("width={{ page_width }}", week)
        self.assertIn("width: {{ page_width }}px;", week)
        self.assertIn("grid-template-columns: 1fr 1fr", week)
        self.assertIn("grid-column: span 2", week)
        self.assertNotRegex(week, r"(?:width=|width:\s*)480(?:px)?")


if __name__ == "__main__":
    unittest.main()
