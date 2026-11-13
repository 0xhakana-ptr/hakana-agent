from __future__ import annotations

import base64
import json
import mimetypes
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import AgentConfig


class PlatformUnavailable(RuntimeError):
    pass


@dataclass
class UploadResult:
    id: str
    slug: str
    review_status: str = ""
    smoke_verdict: str = ""
    raw: dict[str, Any] | None = None


class PlatformClient:
    """Small REST client for the CTFY authoring contract.

    The competition runtime receives a bearer token. Direct REST keeps the
    authoring image free of a CLI/runtime dependency and works with the exact
    same endpoints the official client uses.
    """

    def __init__(self, config: AgentConfig) -> None:
        self.config = config

    @property
    def enabled(self) -> bool:
        return bool(self.config.platform_url and self.config.token and self.config.competition_id)

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        content_type: str = "application/json",
        timeout: int = 60,
    ) -> tuple[int, bytes, dict[str, str]]:
        url = self.config.platform_url.rstrip("/") + "/api/v1" + path
        req = urllib.request.Request(
            url,
            data=body,
            method=method,
            headers={
                "Authorization": f"Bearer {self.config.token}",
                "Accept": "application/json",
                "User-Agent": "QuestionForge/0.1",
                "Content-Type": content_type,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.status, response.read(), dict(response.headers.items())
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read(), dict(exc.headers.items())
        except (urllib.error.URLError, TimeoutError) as exc:
            raise PlatformUnavailable(str(exc)) from exc

    def json(self, method: str, path: str, payload: Any | None = None) -> tuple[int, Any]:
        body = None if payload is None else json.dumps(payload).encode()
        status, raw, _headers = self._request(method, path, body=body)
        try:
            parsed = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            parsed = {"raw": raw.decode("utf-8", "replace")}
        return status, parsed

    def topics(self) -> list[dict[str, Any]]:
        status, data = self.json(
            "GET", f"/competitions/{urllib.parse.quote(self.config.competition_id)}/topics"
        )
        if status != 200 or not isinstance(data, dict):
            return []
        items = data.get("topics")
        return [item for item in items or [] if isinstance(item, dict)]

    def quota(self) -> dict[str, Any]:
        status, data = self.json(
            "GET", f"/competitions/{urllib.parse.quote(self.config.competition_id)}/authoring/quota"
        )
        return data if status == 200 and isinstance(data, dict) else {}

    def uploads(self) -> list[dict[str, Any]]:
        status, data = self.json(
            "GET", f"/competitions/{urllib.parse.quote(self.config.competition_id)}/authored-challenges"
        )
        return data if status == 200 and isinstance(data, list) else []

    def check(
        self,
        archive: bytes,
        *,
        slug: str,
        license_name: str = "platform-only",
        provenance: str = "original",
        ai_assisted: str = "yes",
        destination: str = "public",
        accepted_terms_version: str = "",
    ) -> tuple[int, Any]:
        return self._archive_request(
            f"/competitions/{urllib.parse.quote(self.config.competition_id)}/authored-challenges/check",
            "POST",
            archive,
            slug=slug,
            license_name=license_name,
            provenance=provenance,
            ai_assisted=ai_assisted,
            destination=destination,
            accepted_terms_version=accepted_terms_version,
        )

    def upload(
        self,
        archive: bytes,
        *,
        slug: str,
        license_name: str = "platform-only",
        provenance: str = "original",
        ai_assisted: str = "yes",
        destination: str = "public",
        accepted_terms_version: str = "",
        note: str = "",
        replaces: str = "",
    ) -> tuple[int, Any]:
        return self._archive_request(
            f"/competitions/{urllib.parse.quote(self.config.competition_id)}/authored-challenges",
            "POST",
            archive,
            slug=slug,
            license_name=license_name,
            provenance=provenance,
            ai_assisted=ai_assisted,
            destination=destination,
            accepted_terms_version=accepted_terms_version,
            note=note,
            replaces=replaces,
        )

    def revise(self, challenge_id: str, archive: bytes, *, note: str) -> tuple[int, Any]:
        return self._archive_request(
            f"/competitions/{urllib.parse.quote(self.config.competition_id)}"
            f"/authored-challenges/{urllib.parse.quote(challenge_id)}/revisions",
            "POST",
            archive,
            note=note,
        )

    def _archive_request(
        self,
        path: str,
        method: str,
        archive: bytes,
        **fields: str,
    ) -> tuple[int, Any]:
        boundary = "----QuestionForge" + uuid.uuid4().hex
        parts: list[bytes] = []
        for name, value in fields.items():
            field_name = "license" if name == "license_name" else name
            parts.append(
                (
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="{field_name}"\r\n\r\n'
                    f"{value}\r\n"
                ).encode()
            )
        filename = "challenge.tar.gz"
        parts.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
                "Content-Type: application/gzip\r\n\r\n"
            ).encode()
        )
        parts.append(archive)
        parts.append(f"\r\n--{boundary}--\r\n".encode())
        body = b"".join(parts)
        status, raw, headers = self._request(
            method,
            path,
            body=body,
            content_type=f"multipart/form-data; boundary={boundary}",
            timeout=180,
        )
        try:
            data = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            data = {"raw": raw.decode("utf-8", "replace")}
        if status == 202 and isinstance(data, dict):
            upload_id = str(data.get("upload_id", ""))
            if upload_id:
                for _ in range(40):
                    time.sleep(2)
                    poll_status, poll_data = self.json(
                        "GET",
                        f"/competitions/{urllib.parse.quote(self.config.competition_id)}"
                        f"/authored-uploads/{urllib.parse.quote(upload_id)}",
                    )
                    if poll_status != 202:
                        return poll_status, poll_data
        return status, data

    def smoke_live(self, challenge_id: str) -> dict[str, Any]:
        status, data = self.json(
            "GET",
            f"/competitions/{urllib.parse.quote(self.config.competition_id)}"
            f"/authored-challenges/{urllib.parse.quote(challenge_id)}/smoke-live",
        )
        return data if status == 200 and isinstance(data, dict) else {}

    def smoke_logs(self, challenge_id: str) -> list[dict[str, Any]]:
        status, data = self.json(
            "GET",
            f"/competitions/{urllib.parse.quote(self.config.competition_id)}"
            f"/authored-challenges/{urllib.parse.quote(challenge_id)}/smoke-logs",
        )
        return data if status == 200 and isinstance(data, list) else []

    def wait_for_review(self, challenge_id: str, timeout_s: int) -> dict[str, Any]:
        end = time.monotonic() + timeout_s
        last: dict[str, Any] = {}
        while time.monotonic() < end:
            for row in self.uploads():
                if str(row.get("id")) == challenge_id:
                    last = row
                    if row.get("review_status") in {"approved", "rejected"}:
                        return row
            time.sleep(5)
        return last
