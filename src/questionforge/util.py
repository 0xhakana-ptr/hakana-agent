from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$")


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def slugify(value: str, fallback: str = "signal-forge") -> str:
    out = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    out = re.sub(r"-{2,}", "-", out)
    if len(out) < 3:
        out = fallback
    out = out[:62].rstrip("-")
    if len(out) < 3:
        out = fallback
    return out


def safe_name(value: str, fallback: str) -> str:
    cleaned = "".join(ch for ch in str(value or "") if ch.isprintable() and ch not in "\r\n\t")
    cleaned = cleaned.strip()[:100]
    if not cleaned or any(ch in cleaned for ch in ("<", ">", "\x00")):
        return fallback
    return cleaned


def clean_text(value: str, fallback: str = "", limit: int = 4000) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    text = "".join(ch for ch in text if ch.isprintable() or ch in "\n")
    return (text or fallback)[:limit]


def sanitize_yaml_scalar(value: str) -> str:
    """Return a safe double-quoted YAML scalar without trusting model text."""
    text = clean_text(value, limit=2000)
    return json.dumps(text, ensure_ascii=False)


def atomic_write(path: Path, data: bytes, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        if mode is not None:
            os.chmod(tmp_name, mode)
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def write_text(path: Path, text: str, mode: int | None = None) -> None:
    atomic_write(path, text.encode("utf-8"), mode=mode)


def write_json(path: Path, value: Any) -> None:
    write_text(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@contextmanager
def exclusive_lock(path: Path, timeout_s: float = 10.0) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout_s
    fd: int | None = None
    while fd is None:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            fd = -1
        except FileExistsError:
            try:
                if time.time() - path.stat().st_mtime > 120:
                    path.unlink()
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() >= deadline:
                raise TimeoutError(f"lock timeout: {path}")
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def json_compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
