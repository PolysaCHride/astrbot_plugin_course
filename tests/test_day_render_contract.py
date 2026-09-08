"""Regression checks for the daily schedule render-size contract."""

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
MAIN = (ROOT / "main.py").read_text(encoding="utf-8")


class DayRenderContractTests(unittest.TestCase):
    def test_shared_options_enable_content_sized_full_page_capture(self):
        tree = ast.parse(MAIN)
        options = next(
            node for node in tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "DAY_RENDER_OPTIONS"
                    for target in node.targets)
        )
        values = {
            key.value: ast.literal_eval(value)
            for key, value in zip(options.value.keys, options.value.values)
            if isinstance(key, ast.Constant)
        }
        self.assertEqual(values, {"quality": 100, "full_page": True, "viewport_height": 1})

    def test_both_day_paths_use_copying_helper(self):
        self.assertEqual(MAIN.count("options=_day_render_options()"), 2)
        self.assertIn("return dict(DAY_RENDER_OPTIONS)", MAIN)

    def test_week_paths_keep_week_render_options(self):
        self.assertEqual(MAIN.count('options={"quality": 100}'), 2)
        self.assertEqual(MAIN.count("WEEK_TMPL"), 3)


if __name__ == "__main__":
    unittest.main()
