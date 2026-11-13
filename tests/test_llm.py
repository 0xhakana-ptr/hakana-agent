from __future__ import annotations

import json
import threading
import tempfile
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from questionforge.config import AgentConfig
from questionforge.llm import extract_json_object
from questionforge.llm import ModelClient


class LLMHelperTests(unittest.TestCase):
    def test_json_is_extracted_from_fenced_prose(self) -> None:
        raw = 'Here is the answer:\n```json\n{"candidates": [{"slug": "abc"}]}\n```'
        parsed = extract_json_object(raw)
        self.assertEqual(parsed["candidates"][0]["slug"], "abc")

    def test_json_strings_with_braces_are_not_split(self) -> None:
        raw = 'x {"a":"literal } brace", "b":{"c":1}} trailing'
        parsed = extract_json_object(raw)
        self.assertEqual(parsed["a"], "literal } brace")
        self.assertEqual(parsed["b"]["c"], 1)

    def test_openai_compatible_json_call(self) -> None:
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("content-length", "0"))
                self.rfile.read(length)
                body = json.dumps(
                    {
                        "choices": [
                            {"message": {"role": "assistant", "content": '{"ok":true}'}}
                        ]
                    }
                ).encode()
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        with tempfile.TemporaryDirectory() as tmp:
            config = AgentConfig(
                platform_url="",
                token="",
                competition_id="",
                model_flavor="openai",
                model_base_url=f"http://127.0.0.1:{server.server_address[1]}/v1",
                model_api_key="test",
                model_name="test-model",
                work_dir=Path(tmp),
                deadline_minutes=10,
                dry_run=True,
                upload=False,
                local_smoke=False,
                verbose=False,
            )
            result = ModelClient(config, Path(tmp)).complete_json("system", "prompt")
            self.assertEqual(result, {"ok": True})
        server.shutdown()
        server.server_close()

    def test_auto_backend_falls_back_from_claude_to_direct_api(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = AgentConfig(
                platform_url="",
                token="",
                competition_id="",
                model_flavor="openai",
                model_base_url="https://gateway.example/v1",
                model_api_key="test",
                model_name="test-model",
                work_dir=Path(tmp),
                deadline_minutes=10,
                dry_run=True,
                upload=False,
                local_smoke=False,
                verbose=False,
                model_backend="auto",
            )
            client = ModelClient(config, Path(tmp))
            with mock.patch("questionforge.llm.claude_available", return_value=True), mock.patch(
                "questionforge.llm.call_claude", side_effect=RuntimeError("cli failed")
            ), mock.patch.object(client, "_openai", return_value='{"fallback":true}'):
                result = client.complete_json("system", "prompt")
            self.assertEqual(result, {"fallback": True})
            self.assertEqual(client.stats.backends, {"direct": 1})


if __name__ == "__main__":
    unittest.main()
