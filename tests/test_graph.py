from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from questionforge.graph import FactGraph


class FactGraphTests(unittest.TestCase):
    def test_fact_and_intent_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            graph = FactGraph(Path(tmp) / "graph")
            fact = graph.fact("theme", "test theme")
            intent = graph.intent("build", [fact.id])
            graph.claim(intent.id)
            result = graph.fact("package", "built")
            graph.done(intent.id, result.id)
            text = graph.render()
            self.assertIn("[theme] test theme", text)
            self.assertIn("[done] build -> f0002", text)


if __name__ == "__main__":
    unittest.main()
