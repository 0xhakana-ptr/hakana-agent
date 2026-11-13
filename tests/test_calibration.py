from __future__ import annotations

import json
import importlib.util
import os
import re
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

from questionforge.calibration import CalibrationResult, _BlindHTTPAgent, _decision
from questionforge.recipes import RECIPES


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ScriptedClient:
    available = True

    def __init__(self, expected: dict[str, str]) -> None:
        self.expected = expected
        self.calls = 0
        self.prompts: list[str] = []

    def complete_json(self, system: str, prompt: str, *, max_tokens: int = 0):
        self.calls += 1
        self.prompts.append(prompt)
        state = json.loads(prompt)
        transcript = state["transcript"]
        if self.calls == 1:
            return {
                "action": "request",
                "method": "GET",
                "path": "/api/query?id=public-index&depth=6",
            }
        if self.calls == 2:
            body = transcript[-1]["observation"]["body"]
            checkpoint = re.search(r"FLAG\{[0-9a-f]{32}\}", body).group(0)
            return {"action": "submit", "question_id": "checkpoint", "value": checkpoint}
        if self.calls == 3:
            body = transcript[0]["observation"]["body"]
            export_path = json.loads(body)["expanded"][0]["expanded"][0]["export_path"]
            return {"action": "request", "method": "GET", "path": export_path}
        body = transcript[-1]["observation"]["body"]
        master = re.search(r"FLAG\{[0-9a-f]{32}\}", body).group(0)
        return {"action": "submit", "question_id": "master_key", "value": master}


class CalibrationTests(unittest.TestCase):
    def test_sweet_spot_is_kept(self) -> None:
        status, level, _ = _decision(0.12, 1)
        self.assertEqual(status, "in_band")
        self.assertEqual(level, 1)

    def test_too_easy_raises_one_level(self) -> None:
        status, level, _ = _decision(0.60, 1)
        self.assertEqual(status, "too_easy")
        self.assertEqual(level, 2)

    def test_too_hard_lowers_one_level(self) -> None:
        status, level, _ = _decision(0.00, 2)
        self.assertEqual(status, "too_hard")
        self.assertEqual(level, 1)

    def test_estimate_does_not_force_adjustment(self) -> None:
        result = CalibrationResult("estimate", 0, 0, 0.8, "estimated", "low", 1, 1)
        self.assertFalse(result.should_adjust)

    def test_single_external_trial_cannot_force_adjustment(self) -> None:
        result = CalibrationResult("live", 1, 1, 1.0, "too_easy", "low", 1, 2)
        self.assertFalse(result.should_adjust)

    def test_blind_http_agent_solves_only_through_public_service(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recipe = RECIPES["web-object-graph"]
            blueprint = recipe.default_blueprint("linked records")
            recipe.build(blueprint, root / blueprint.slug)
            answers = root / "answers"
            answers.mkdir()
            checkpoint = "FLAG{11111111111111111111111111111111}"
            master = "FLAG{22222222222222222222222222222222}"
            (answers / "checkpoint").write_text(checkpoint, encoding="utf-8")
            (answers / "master_key").write_text(master, encoding="utf-8")
            old = os.environ.get("ANSWER_DIR")
            os.environ["ANSWER_DIR"] = str(answers)
            try:
                module = load_module(
                    root / blueprint.slug / "services/app/app.py",
                    "qforge_blind_http_test",
                )
                server = ThreadingHTTPServer(("127.0.0.1", 0), module.Handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                client = ScriptedClient({"checkpoint": checkpoint, "master_key": master})
                agent = _BlindHTTPAgent(
                    client,  # type: ignore[arg-type]
                    blueprint=blueprint,
                    package_dir=root / blueprint.slug,
                    target_url=f"http://127.0.0.1:{server.server_address[1]}",
                    expected={"checkpoint": checkpoint, "master_key": master},
                    max_turns=6,
                )
                solved, trace = agent.run()
                self.assertTrue(solved)
                self.assertTrue(any(item.get("kind") == "observation" for item in trace))
                self.assertTrue(all("services/app.py" not in prompt for prompt in client.prompts))
                server.shutdown()
                server.server_close()
            finally:
                if old is None:
                    os.environ.pop("ANSWER_DIR", None)
                else:
                    os.environ["ANSWER_DIR"] = old


if __name__ == "__main__":
    unittest.main()
