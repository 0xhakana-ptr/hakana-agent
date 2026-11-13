from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from questionforge.config import AgentConfig
from questionforge.platform import PlatformClient


class PlatformMultipartTests(unittest.TestCase):
    def test_upload_multipart_has_archive_and_declarations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = AgentConfig(
                platform_url="https://example.invalid",
                token="test-token",
                competition_id="event-id",
                model_flavor="openai",
                model_base_url="",
                model_api_key="",
                model_name="",
                work_dir=Path(tmp),
                deadline_minutes=10,
                dry_run=False,
                upload=True,
                local_smoke=False,
                verbose=False,
            )
            client = PlatformClient(config)
            captured: dict[str, object] = {}

            def fake_request(method, path, **kwargs):
                captured.update(method=method, path=path, **kwargs)
                return 201, b'{"id":"AUTHORED-12345678"}', {}

            client._request = fake_request  # type: ignore[method-assign]
            status, data = client.upload(
                b"archive-bytes",
                slug="my-challenge",
                note="test build",
            )
            self.assertEqual(status, 201)
            self.assertEqual(data["id"], "AUTHORED-12345678")
            body = bytes(captured["body"])
            self.assertIn(b'name="slug"', body)
            self.assertIn(b"my-challenge", body)
            self.assertIn(b'name="license"', body)
            self.assertIn(b"platform-only", body)
            self.assertIn(b'name="ai_assisted"', body)
            self.assertIn(b"archive-bytes", body)
            self.assertTrue(str(captured["content_type"]).startswith("multipart/form-data; boundary="))


if __name__ == "__main__":
    unittest.main()
