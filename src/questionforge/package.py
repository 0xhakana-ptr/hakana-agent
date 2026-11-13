from __future__ import annotations

import io
import os
import tarfile
from pathlib import Path

from .util import sha256_bytes


SKIP_NAMES = {".git", "__pycache__", "node_modules", ".venv", ".DS_Store"}


def pack_directory(package_dir: Path) -> tuple[bytes, str, list[str]]:
    """Pack a CTFY challenge with one root directory, refusing special files."""
    package_dir = package_dir.resolve()
    if not (package_dir / "metadata.yaml").is_file():
        raise ValueError("metadata.yaml is not at package root")
    skipped: list[str] = []
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz", format=tarfile.PAX_FORMAT) as archive:
        for path in sorted(package_dir.rglob("*")):
            rel = path.relative_to(package_dir)
            if any(part in SKIP_NAMES for part in rel.parts):
                skipped.append(str(rel).replace(os.sep, "/"))
                continue
            if path.is_symlink() or (path.exists() and not (path.is_file() or path.is_dir())):
                raise ValueError(f"special or symlink member refused: {rel}")
            if not path.is_file():
                continue
            data = path.read_bytes()
            info = tarfile.TarInfo(f"{package_dir.name}/{rel.as_posix()}")
            info.size = len(data)
            info.mode = 0o755 if os.access(path, os.X_OK) and not os.name == "nt" else 0o644
            info.mtime = int(path.stat().st_mtime)
            archive.addfile(info, io.BytesIO(data))
    blob = buf.getvalue()
    return blob, sha256_bytes(blob), skipped
