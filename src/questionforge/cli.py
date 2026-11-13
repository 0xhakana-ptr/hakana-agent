from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
from pathlib import Path

from . import __version__
from .config import AgentConfig
from .claude_cli import available as claude_available, version as claude_version
from .graph import FactGraph
from .models import Blueprint
from .orchestrator import Orchestrator
from .package import pack_directory
from .planner import fallback_blueprint
from .recipes import RECIPES, recipe_catalog
from .util import read_json, write_json
from .verify import run_ctfy_check, static_verify


def _base_config(args: argparse.Namespace) -> AgentConfig:
    cfg = AgentConfig.from_env(
        work_dir=getattr(args, "work_dir", "") or "",
        dry_run=bool(getattr(args, "dry_run", False)),
        upload=not bool(getattr(args, "no_upload", False)),
    )
    return cfg.with_overrides(
        competition_id=getattr(args, "competition", None),
        deadline_minutes=getattr(args, "deadline_minutes", None),
        upload=not bool(getattr(args, "no_upload", False)),
        local_smoke=True if getattr(args, "local_smoke", False) else None,
        calibration=False if getattr(args, "no_calibration", False) else None,
        calibration_trials=getattr(args, "calibration_trials", None),
    )


def _cmd_run(args: argparse.Namespace) -> int:
    cfg = _base_config(args)
    run_dir = Orchestrator(cfg).run(args.theme or "")
    result = read_json(run_dir / "result.json", {})
    print(json.dumps({"run_dir": str(run_dir), "status": result.get("status")}, ensure_ascii=False))
    return 0 if result.get("status") not in {"rejected-local", "rejected-platform-check", "rejected-platform-upload"} else 2


def _cmd_build(args: argparse.Namespace) -> int:
    selected = str(args.recipe or "")
    if selected:
        if selected not in RECIPES:
            raise SystemExit(f"unknown recipe: {selected}")
        raw = RECIPES[selected].default_blueprint(args.theme)
    else:
        raw = fallback_blueprint(args.theme)
    if getattr(args, "difficulty_level", None) is not None:
        params = dict(raw.parameters)
        params["difficulty_level"] = args.difficulty_level
        from dataclasses import replace

        raw = replace(raw, parameters=params)
    blueprint = raw
    output = Path(args.output)
    result = RECIPES[blueprint.recipe].build(blueprint, output)
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))
    return 0


def _cmd_plan(args: argparse.Namespace) -> int:
    blueprint = fallback_blueprint(args.theme)
    if getattr(args, "difficulty_level", None) is not None:
        from dataclasses import replace

        params = dict(blueprint.parameters)
        params["difficulty_level"] = args.difficulty_level
        blueprint = replace(blueprint, parameters=params)
    output = Path(args.output)
    write_json(output, blueprint.to_dict())
    print(output)
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    package = Path(args.package)
    manifest = read_json(package / "BUILD_MANIFEST.json", {}) or {}
    recipe_id = str(manifest.get("recipe", "web-preview-ssrf"))
    blueprint = RECIPES.get(recipe_id, RECIPES["web-preview-ssrf"]).default_blueprint("verify")
    report = static_verify(package, blueprint)
    if not args.no_ctfy:
        run_ctfy_check(package, report)
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 0 if report.ok else 1


def _cmd_pack(args: argparse.Namespace) -> int:
    blob, digest, skipped = pack_directory(Path(args.package))
    output = Path(args.output)
    output.write_bytes(blob)
    print(json.dumps({"path": str(output), "sha256": digest, "skipped": skipped}, ensure_ascii=False))
    return 0


def _cmd_graph(args: argparse.Namespace) -> int:
    graph = FactGraph(Path(args.run_dir) / "graph")
    print(graph.render())
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    cfg = AgentConfig.from_env(upload=False)
    checks = {
        "python": sys.version.split()[0],
        "ctfy": shutil.which("ctfy") or "",
        "docker": shutil.which("docker") or "",
        "model_backend": cfg.model_backend,
        "claude_code": {
            "installed": bool(shutil.which(cfg.claude_bin)),
            "authenticated_for_run": claude_available(cfg),
            "version": claude_version(cfg),
            "path": shutil.which(cfg.claude_bin) or "",
        },
        "model_available": bool(cfg.model_base_url and cfg.model_api_key and cfg.model_name),
        "platform_configured": bool(cfg.platform_url and cfg.token and cfg.competition_id),
        "calibration": {
            "enabled": cfg.calibration,
            "trials": cfg.calibration_trials,
            "turns": cfg.calibration_turns,
            "external_target": bool(cfg.calibration_target),
        },
        "work_dir": str(cfg.work_dir),
        "recipes": recipe_catalog(),
    }
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="questionforge",
        description="Autonomous CTFY/TPCTF challenge authoring agent",
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run the full autonomous authoring workflow")
    run.add_argument("--theme", default="", help="round topic; otherwise read env or platform topics")
    run.add_argument("--competition", default=None)
    run.add_argument("--work-dir", default="")
    run.add_argument("--deadline-minutes", type=int, default=None)
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--no-upload", action="store_true")
    run.add_argument("--local-smoke", action="store_true")
    run.add_argument("--no-calibration", action="store_true")
    run.add_argument("--calibration-trials", type=int, default=None)
    run.set_defaults(func=_cmd_run)

    build = sub.add_parser("build", help="build a deterministic offline package")
    build.add_argument("--theme", required=True)
    build.add_argument("--recipe", choices=sorted(RECIPES), default="")
    build.add_argument("--difficulty-level", type=int, choices=(0, 1, 2), default=None)
    build.add_argument("--output", required=True)
    build.set_defaults(func=_cmd_build)

    plan = sub.add_parser("plan", help="write a deterministic blueprint")
    plan.add_argument("--theme", required=True)
    plan.add_argument("--output", required=True)
    plan.add_argument("--difficulty-level", type=int, choices=(0, 1, 2), default=None)
    plan.set_defaults(func=_cmd_plan)

    verify = sub.add_parser("verify", help="run structural checks and ctfy authoring check")
    verify.add_argument("package")
    verify.add_argument("--no-ctfy", action="store_true")
    verify.set_defaults(func=_cmd_verify)

    pack = sub.add_parser("pack", help="pack a directory as CTFY-compatible tar.gz")
    pack.add_argument("package")
    pack.add_argument("--output", required=True)
    pack.set_defaults(func=_cmd_pack)

    graph = sub.add_parser("graph", help="print a run's fact/intent graph")
    graph.add_argument("run_dir")
    graph.set_defaults(func=_cmd_graph)

    doctor = sub.add_parser("doctor", help="show runtime capabilities")
    doctor.set_defaults(func=_cmd_doctor)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if os.environ.get("AUTHORING_VERBOSE") == "1" else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"questionforge: {exc}", file=sys.stderr)
        return 1
