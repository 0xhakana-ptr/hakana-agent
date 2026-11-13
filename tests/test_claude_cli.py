from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from questionforge.claude_cli import call_claude
from questionforge.config import AgentConfig


class ClaudeCliTests(unittest.TestCase):
    def test_headless_call_disables_tools_and_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = AgentConfig(
                platform_url="",
                token="",
                competition_id="",
                model_flavor="anthropic",
                model_base_url="https://gateway.example",
                model_api_key="test-key",
                model_name="test-model",
                work_dir=Path(tmp),
                deadline_minutes=10,
                dry_run=True,
                upload=False,
                local_smoke=False,
                verbose=False,
                model_backend="claude_cli",
            )
            completed = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=json.dumps(
                    {
                        "type": "result",
                        "is_error": False,
                        "result": '{"ok":true}',
                        "session_id": "test-session",
                    }
                ),
                stderr="",
            )
            with mock.patch("questionforge.claude_cli.shutil.which", return_value="/usr/bin/claude"), mock.patch(
                "questionforge.claude_cli.subprocess.run", return_value=completed
            ) as run:
                text, metadata = call_claude(
                    config,
                    run_dir=Path(tmp),
                    system="system prompt",
                    prompt="user prompt",
                    max_tokens=1000,
                    effort="high",
                )
            self.assertEqual(text, '{"ok":true}')
            self.assertEqual(metadata["session_id"], "test-session")
            command = run.call_args.args[0]
            self.assertIn("--bare", command)
            self.assertIn("--restricted", command)
            self.assertIn("--tools", command)
            self.assertIn("", command)
            self.assertIn("--no-session-persistence", command)
            self.assertNotIn("--dangerously-skip-permissions", command)
            env = run.call_args.kwargs["env"]
            self.assertEqual(env["ANTHROPIC_API_KEY"], "test-key")
            self.assertEqual(env["ANTHROPIC_BASE_URL"], "https://gateway.example")


if __name__ == "__main__":
    unittest.main()
