from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from questionforge.recipes import RECIPES
from questionforge.verify import static_verify


class RecipeTests(unittest.TestCase):
    def test_each_recipe_builds_and_passes_internal_gate(self) -> None:
        for recipe_id, recipe in RECIPES.items():
            with self.subTest(recipe=recipe_id), tempfile.TemporaryDirectory() as tmp:
                blueprint = recipe.default_blueprint("operator workflows")
                output = Path(tmp) / blueprint.slug
                result = recipe.build(blueprint, output)
                self.assertGreater(len(result.files), 7)
                report = static_verify(output, blueprint)
                self.assertTrue(report.ok, [i.to_dict() for i in report.issues])
                metadata = (output / "metadata.yaml").read_text(encoding="utf-8")
                self.assertIn("standard: CTFY-0002/1", metadata)
                self.assertIn("requires:", metadata)
                self.assertNotRegex(metadata, r"(?m)^\s{4}answer:")

    def test_two_dynamic_answers_are_wired(self) -> None:
        for recipe in RECIPES.values():
            with self.subTest(recipe=recipe.info.id), tempfile.TemporaryDirectory() as tmp:
                blueprint = recipe.default_blueprint("operator workflows")
                output = Path(tmp) / blueprint.slug
                recipe.build(blueprint, output)
                compose = (output / "docker-compose.yml").read_text(encoding="utf-8")
                rotate = (output / "services/flag-rotator/rotate.sh").read_text(encoding="utf-8")
                self.assertIn("ANSWER_CHECKPOINT", compose)
                self.assertIn("ANSWER_MASTER_KEY", compose)
                self.assertIn("/out/checkpoint", rotate)
                self.assertIn("/out/master_key", rotate)


if __name__ == "__main__":
    unittest.main()
