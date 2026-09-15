"""Regression checks for the shared adaptive schedule render contract."""

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
MAIN = (ROOT / "main.py").read_text(encoding="utf-8")


class ScheduleRenderContractTests(unittest.TestCase):
    def test_shared_options_are_complete_and_isolated(self):
        tree = ast.parse(MAIN)
        assignment = next(
            node for node in tree.body
            if isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "SCHEDULE_RENDER_OPTIONS"
        )
        self.assertIsInstance(assignment.value, ast.Call)
        self.assertEqual(getattr(assignment.value.func, "id", None), "MappingProxyType")
        values = ast.literal_eval(assignment.value.args[0])
        self.assertEqual(values, {"quality": 100, "full_page": True, "viewport_height": 1})
        self.assertIn("return dict(SCHEDULE_RENDER_OPTIONS)", MAIN)

    def test_every_schedule_path_uses_the_isolated_helper(self):
        tree = ast.parse(MAIN)
        render_calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "html_render"
        ]
        self.assertEqual(len(render_calls), 4)
        for call in render_calls:
            options = next(keyword for keyword in call.keywords if keyword.arg == "options")
            self.assertIsInstance(options.value, ast.Call)
            self.assertEqual(getattr(options.value.func, "id", None), "_schedule_render_options")


if __name__ == "__main__":
    unittest.main()
