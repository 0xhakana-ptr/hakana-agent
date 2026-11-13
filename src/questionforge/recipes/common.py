from __future__ import annotations

import hashlib
import html
import json
import os
from pathlib import Path
from typing import Iterable

from ..models import Blueprint, BuildResult
from ..util import safe_name, sanitize_yaml_scalar, slugify, write_text


def q(value: str) -> str:
    return sanitize_yaml_scalar(value)


def answers_manifest(blueprint: Blueprint) -> list[str]:
    ids = [question.id for question in blueprint.questions]
    return ids or ["checkpoint", "master_key"]


def metadata_yaml(blueprint: Blueprint) -> str:
    questions = list(blueprint.questions)
    if not questions:
        questions = []
    lines = [
        "standard: CTFY-0002/1",
        f"name: {q(blueprint.title)}",
        "description: |",
    ]
    lines.extend(f"  {line}" for line in blueprint.description.strip().splitlines())
    lines.extend(
        [
            f"difficulty: {blueprint.difficulty}",
            f"category: {blueprint.category}",
            "tags:",
            *[f"  - {q(tag)}" for tag in blueprint.tags],
            "questions:",
        ]
    )
    for question in questions:
        lines.extend(
            [
                f"  - id: {question.id}",
                f"    prompt: {q(question.prompt)}",
                f"    weight: {question.weight}",
            ]
        )
        if question.requires:
            lines.append("    requires:")
            lines.extend(f"      - {item}" for item in question.requires)
    return "\n".join(lines) + "\n"


def rotator_files(answer_ids: Iterable[str]) -> dict[str, str]:
    ids = list(answer_ids)
    writes = "\n".join(
        'printf "%s" "${ANSWER_' + item.upper() + '}" > "/out/' + item + '"'
        for item in ids
    )
    checks = " && ".join(f'test -s "/out/{item}"' for item in ids)
    dockerfile = """\
FROM python:3.12-slim-bookworm
COPY rotate.sh /rotate.sh
CMD ["sh", "/rotate.sh"]
"""
    rotate = f"""\
#!/bin/sh
set -eu
{writes}
"""
    return {
        "services/flag-rotator/Dockerfile": dockerfile,
        "services/flag-rotator/rotate.sh": rotate,
        "_rotator_check": checks,
    }


def compose_yaml(
    blueprint: Blueprint,
    *,
    app_service: str,
    extra_services: str,
    app_port: int | None = 8080,
    protocol: str = "http",
    app_depends: list[str] | None = None,
    builder: str = "",
    app_health_entry: str = "/app/app.py",
) -> str:
    answer_ids = answers_manifest(blueprint)
    env = "\n".join(f"      - ANSWER_{item.upper()}" for item in answer_ids)
    checks = " && ".join(f'test -s "/out/{item}"' for item in answer_ids)
    deps = app_depends or []
    depends_yaml = ""
    if deps:
        depends_yaml = "    depends_on:\n"
        for dep in deps:
            condition = (
                "service_completed_successfully"
                if dep == "flag-rotator"
                else "service_healthy"
            )
            depends_yaml += f"      {dep}:\n        condition: {condition}\n"
    port_yaml = ""
    protocol_label = ""
    if app_port is not None:
        port_yaml = f"    ports:\n      - \"{app_port}:{app_port}\"\n"
        protocol_label = f"    labels:\n      ctfy.service.protocol: {protocol}\n"
    return f"""\
services:
  flag-rotator:
    deploy:
      resources:
        limits:
          cpus: "0.2"
          memory: 64M
    build:
      context: ./services/flag-rotator
    environment:
{env}
    volumes:
      - answers:/out
    restart: "no"
    healthcheck:
      test: {json.dumps(["CMD", "sh", "-c", checks])}
      interval: 1s
      timeout: 1s
      retries: 30
      start_period: 1s

  {app_service}:
    deploy:
      resources:
        limits:
          cpus: "0.5"
          memory: 384M
    build:
      context: ./services/{app_service}
{depends_yaml}{port_yaml}{protocol_label}    volumes:
      - type: volume
        source: answers
        target: /answers
        read_only: true
    healthcheck:
      test: {json.dumps(["CMD", "python3", app_health_entry, "--health"])}
      interval: 5s
      timeout: 3s
      retries: 20
      start_period: 3s

{extra_services.rstrip()}
{builder.rstrip()}

volumes:
  answers:
"""


def finalize(blueprint: Blueprint, destination: Path) -> BuildResult:
    files = sorted(
        str(path.relative_to(destination)).replace(os.sep, "/")
        for path in destination.rglob("*")
        if path.is_file()
    )
    digest = hashlib.sha256()
    for rel in files:
        digest.update(rel.encode())
        digest.update((destination / rel).read_bytes())
    write_text(
        destination / "BUILD_MANIFEST.json",
        json.dumps(
            {
                "slug": blueprint.slug,
                "recipe": blueprint.recipe,
                "sha256": digest.hexdigest(),
                "files": files,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )
    return BuildResult(str(destination), files + ["BUILD_MANIFEST.json"], digest.hexdigest())


def authoring_note(blueprint: Blueprint) -> str:
    shortcuts = "; ".join(blueprint.anti_shortcuts) or "none stated"
    return f"""\
# {blueprint.title}

Generated by QuestionForge from the `{blueprint.recipe}` compiler.

Round theme: {blueprint.theme}

This file is authoring metadata and is not shown to players.
The public brief is `metadata.yaml`; the secret intended path below must never
be copied into player-visible content.

## Secret intended path

{blueprint.intended}

Shortcuts that do not count: {shortcuts}
"""


def templated_css() -> str:
    return """\
:root { color-scheme: dark; --bg:#11151c; --panel:#1a2130; --ink:#e9eef8; --muted:#93a1b8; --accent:#65e2b5; }
* { box-sizing: border-box; }
body { margin:0; font:15px/1.55 ui-monospace, SFMono-Regular, Consolas, monospace; background:var(--bg); color:var(--ink); }
main { width:min(920px,92vw); margin:48px auto; }
.card { background:var(--panel); border:1px solid #2d3950; border-radius:12px; padding:22px; margin:16px 0; }
a { color:var(--accent); }
.muted { color:var(--muted); }
input, textarea, button { width:100%; padding:10px; border-radius:8px; border:1px solid #3c4b65; background:#0d1118; color:var(--ink); font:inherit; }
button { margin-top:10px; cursor:pointer; background:#174f43; }
pre { white-space:pre-wrap; overflow-wrap:anywhere; }
"""


def escape(value: str) -> str:
    return html.escape(value, quote=True)
