from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from questionforge.models import Blueprint
from questionforge.planner import fallback_blueprint, normalize_blueprint
from questionforge.recipes import RECIPES
from questionforge.verify import static_verify


class PlannerTests(unittest.TestCase):
    def test_theme_classification_and_normalization(self) -> None:
        ai = fallback_blueprint("AI agent tool context and prompt safety")
        pwn = fallback_blueprint("binary memory and stack control")
        web = fallback_blueprint("managed archive portal")
        self.assertEqual(ai.recipe, "ai-tool-agent")
        self.assertEqual(pwn.recipe, "pwn-stack-chain")
        self.assertEqual(web.recipe, "web-preview-ssrf")
        self.assertGreaterEqual(ai.estimated_agent_solve_rate, 0.0)
        self.assertLessEqual(ai.estimated_agent_solve_rate, 1.0)

    def test_exposed_technique_in_description_is_rejected(self) -> None:
        raw = RECIPES["web-preview-ssrf"].default_blueprint("archive")
        broken = Blueprint.from_dict(
            {
                **raw.to_dict(),
                "description": "Use SSRF to read the answer.",
            }
        )
        with self.assertRaises(ValueError):
            normalize_blueprint(broken)


class ValidatorTests(unittest.TestCase):
    def test_literal_flag_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            blueprint = RECIPES["ai-tool-agent"].default_blueprint("agent")
            RECIPES["ai-tool-agent"].build(blueprint, root / blueprint.slug)
            package = root / blueprint.slug
            app = package / "services/app/app.py"
            app.write_text(app.read_text() + "\nSTOLEN = 'FLAG{do_not_ship}'\n", encoding="utf-8")
            report = static_verify(package, blueprint)
            self.assertFalse(report.ok)
            self.assertIn("literal_flag_in_services", {item.code for item in report.issues})


if __name__ == "__main__":
    unittest.main()
