from __future__ import annotations

import json
import logging
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from .config import AgentConfig
from .calibration import calibrate
from .graph import FactGraph
from .llm import ModelClient, model_review, request_repair
from .models import Blueprint
from .package import pack_directory
from .planner import plan
from .platform import PlatformClient, PlatformUnavailable
from .recipes import RECIPES
from .report import write_reports
from .util import clean_text, slugify, utc_now, write_json
from .verify import run_ctfy_check, run_local_smoke, static_verify

log = logging.getLogger("questionforge")


class Orchestrator:
    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        self.run_id = time.strftime("%Y%m%d-%H%M%S", time.localtime())

    def _released_topic(self, api: PlatformClient) -> str:
        try:
            for topic in reversed(api.topics()):
                if not topic.get("released", True):
                    continue
                title = topic.get("title") or {}
                body = topic.get("body") or {}
                if isinstance(title, dict):
                    title = title.get("zh-CN") or title.get("en") or ""
                if isinstance(body, dict):
                    body = body.get("zh-CN") or body.get("en") or ""
                combined = clean_text(f"{title}\n{body}", limit=5000)
                if combined:
                    return combined
        except PlatformUnavailable:
            return ""
        return ""

    def _task_json_topic(self) -> str:
        task = self.config.work_dir / "task.json"
        try:
            payload = json.loads(task.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return ""
        if not isinstance(payload, dict):
            return ""
        for key in ("authoring_topic", "topic", "theme", "subject"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value
        challenge = payload.get("challenge")
        if isinstance(challenge, dict):
            for key in ("authoring_topic", "topic", "theme", "description"):
                value = challenge.get(key)
                if isinstance(value, str) and value.strip():
                    return value
        return ""

    def run(self, theme: str = "") -> Path:
        start = time.monotonic()
        deadline = start + max(30, self.config.deadline_minutes * 60)
        run_dir = self.config.work_dir / "runs" / self.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        graph = FactGraph(run_dir / "graph")
        api = PlatformClient(self.config)
        if not theme:
            theme = (
                __import__("os").environ.get("AUTHORING_TOPIC")
                or __import__("os").environ.get("CTFY_TOPIC")
                or self._task_json_topic()
                or self._released_topic(api)
            )
        theme = clean_text(theme, "resilient operator workflows and protected handoffs", limit=8000)
        log.info("run=%s theme=%r", self.run_id, theme[:160])
        graph.fact("theme", "Round theme received", data={"theme": theme}, creator="platform")

        quota = api.quota() if api.enabled else {}
        write_json(run_dir / "context.json", {"theme": theme, "quota": quota})
        client = ModelClient(self.config, run_dir)
        blueprint = plan(theme=theme, client=client, graph=graph)
        log.info("selected recipe=%s title=%r estimated_rate=%.1f%%", blueprint.recipe, blueprint.title, blueprint.estimated_agent_solve_rate * 100)
        graph.fact(
            "blueprint",
            f"Selected {blueprint.title}",
            data=blueprint.to_dict(),
        )
        package_dir = run_dir / "package" / slugify(blueprint.slug)
        recipe = RECIPES[blueprint.recipe]
        intent = graph.intent("compile, validate, smoke and submit one themed challenge", ["f0001", "f0002"])
        graph.claim(intent.id)
        build = recipe.build(blueprint, package_dir)
        log.info("package built at %s (%d files)", package_dir, len(build.files))
        graph.fact(
            "package_built",
            f"Built {len(build.files)} files",
            data={"package_dir": str(package_dir), "sha256": build.sha256},
        )

        report = static_verify(package_dir, blueprint)
        run_ctfy_check(package_dir, report)
        if report.ok and self.config.local_smoke and time.monotonic() < deadline:
            run_local_smoke(package_dir, report)
        log.info("static verification=%s audit=%s smoke=%s", report.ok, report.audit_ok, report.local_smoke)

        review: dict[str, Any] | None = None
        calibration: dict[str, Any] | None = None
        reviewed_files: dict[str, str] = {}
        if client.available and report.ok:
            reviewed_files = {
                str(path.relative_to(package_dir)).replace("\\", "/"): path.read_text(
                    encoding="utf-8", errors="replace"
                )
                for path in package_dir.rglob("*")
                if path.is_file() and path.stat().st_size < 200_000
            }
            if sum(len(text) for text in reviewed_files.values()) < 200_000:
                try:
                    review = model_review(client, blueprint, reviewed_files)
                    graph.fact("adversarial_review", review.get("verdict", "unknown"), data=review)
                    if review.get("severity") == "critical":
                        report.add("critical_review", "error", "", "adversarial review found a critical flaw")
                    log.info("adversarial review=%s severity=%s", review.get("verdict"), review.get("severity"))
                except Exception as exc:
                    graph.fact("review_unavailable", str(exc))

        if (
            review
            and review.get("verdict") != "pass"
            and client.available
            and time.monotonic() < deadline
        ):
            try:
                repair = request_repair(
                    client,
                    blueprint=blueprint,
                    failure=json.dumps(review, ensure_ascii=False),
                    files=reviewed_files,
                )
                patched = self._apply_repair(blueprint, repair)
                if patched is not None:
                    repaired_dir = run_dir / "package" / (slugify(patched.slug) + "-repair")
                    RECIPES[patched.recipe].build(patched, repaired_dir)
                    repaired_report = static_verify(repaired_dir, patched)
                    run_ctfy_check(repaired_dir, repaired_report)
                    if repaired_report.ok:
                        blueprint = patched
                        package_dir = repaired_dir
                        report = repaired_report
                        graph.fact(
                            "repair",
                            "accepted a bounded model-guided parameter repair",
                            data={"strategy": repair.get("strategy"), "reason": repair.get("reason")},
                        )
                    else:
                        graph.fact("repair", "rejected because the regenerated tree failed validation")
            except Exception as exc:
                graph.fact("repair_unavailable", str(exc))

        if report.ok and self.config.calibration and time.monotonic() < deadline:
            try:
                measured = calibrate(
                    config=self.config,
                    client=client,
                    blueprint=blueprint,
                    package_dir=package_dir,
                    run_dir=run_dir,
                )
                calibration = measured.to_dict()
                graph.fact(
                    "difficulty_calibration",
                    f"{measured.status} rate={measured.solve_rate:.1%}",
                    data=calibration,
                )
                log.info(
                    "difficulty calibration source=%s status=%s rate=%.1f%% level=%d",
                    measured.source,
                    measured.status,
                    measured.solve_rate * 100,
                    measured.current_difficulty_level,
                )
                if measured.should_adjust:
                    params = dict(blueprint.parameters)
                    params["difficulty_level"] = measured.suggested_difficulty_level
                    adjusted = replace(blueprint, parameters=params)
                    adjusted_dir = run_dir / "package" / (slugify(adjusted.slug) + "-calibrated")
                    RECIPES[adjusted.recipe].build(adjusted, adjusted_dir)
                    adjusted_report = static_verify(adjusted_dir, adjusted)
                    run_ctfy_check(adjusted_dir, adjusted_report)
                    if adjusted_report.ok and self.config.local_smoke and time.monotonic() < deadline:
                        run_local_smoke(adjusted_dir, adjusted_report)
                    if adjusted_report.ok:
                        blueprint = adjusted
                        package_dir = adjusted_dir
                        report = adjusted_report
                        graph.fact(
                            "difficulty_adjustment",
                            f"level {measured.current_difficulty_level} -> {measured.suggested_difficulty_level}",
                            data=calibration,
                        )
                        log.info(
                            "difficulty adjusted %d -> %d",
                            measured.current_difficulty_level,
                            measured.suggested_difficulty_level,
                        )
            except Exception as exc:
                graph.fact("calibration_unavailable", str(exc))

        archive, archive_sha, skipped = pack_directory(package_dir)
        if skipped:
            graph.fact("packing", "library directories omitted", data={"skipped": skipped})
        result: dict[str, Any] | None = None
        status = "prepared" if report.ok else "rejected-local"
        if report.ok and self.config.upload and api.enabled and time.monotonic() < deadline:
            status, result = self._publish(api, archive, blueprint, graph, deadline)
        elif report.ok and self.config.upload and not api.enabled:
            graph.fact("publish_skipped", "platform URL, token, or competition id is missing")
            status = "prepared-offline"
        graph.fact("run_status", status, data={"archive_sha256": archive_sha})
        log.info("status=%s report=%s", status, run_dir / "RUN_REPORT.md")
        if status in {"approved", "prepared", "prepared-offline"}:
            graph.done(intent.id, graph.facts()[-1].id)
        else:
            graph.fail(intent.id, status)
        write_reports(
            run_dir,
            blueprint=blueprint,
            package_dir=package_dir,
            archive=archive,
            report=report,
            model_review=review,
            calibration=calibration,
            platform_result=result,
            status=status,
        )
        return run_dir

    @staticmethod
    def _apply_repair(blueprint: Blueprint, repair: dict[str, Any]) -> Blueprint | None:
        changes = repair.get("blueprint_patch")
        if not isinstance(changes, dict):
            changes = {}
        params = repair.get("parameter_patch")
        if isinstance(params, dict):
            merged = dict(blueprint.parameters)
            for key, value in params.items():
                if isinstance(key, str) and isinstance(value, (str, int, float, bool)):
                    merged[key] = value
            changes = {**changes, "parameters": merged}
        allowed = {
            "title",
            "description",
            "difficulty",
            "tags",
            "anti_shortcuts",
            "parameters",
            "estimated_agent_solve_rate",
            "rationale",
            "risk",
            "intended",
        }
        safe = {key: value for key, value in changes.items() if key in allowed}
        if not safe:
            return None
        raw = blueprint.to_dict()
        raw.update(safe)
        try:
            from .planner import normalize_blueprint

            return normalize_blueprint(Blueprint.from_dict(raw))
        except (KeyError, TypeError, ValueError):
            return None

    def _publish(
        self,
        api: PlatformClient,
        archive: bytes,
        blueprint: Blueprint,
        graph: FactGraph,
        deadline: float,
    ) -> tuple[str, dict[str, Any]]:
        quota = api.quota()
        window = quota.get("upload_window") or {}
        rate = quota.get("upload_rate") or {}
        if window.get("remaining") == 0:
            graph.fact("publish_skipped", "authoring window has no new-challenge quota remaining")
            return "prepared-window-closed", {"quota": quota}
        if rate.get("remaining") == 0:
            graph.fact("publish_skipped", "rolling upload rate is exhausted")
            return "prepared-rate-limited", {"quota": quota}

        status, checked = api.check(archive, slug=blueprint.slug)
        write_json(graph.root.parent / "platform-check.json", checked)
        graph.fact(
            "platform_check",
            f"HTTP {status}",
            data={"status": status, "response": checked},
        )
        if status >= 400 or (isinstance(checked, dict) and checked.get("ok") is False):
            return "rejected-platform-check", {"check": checked, "status": status, "quota": quota}
        status, uploaded = api.upload(
            archive,
            slug=blueprint.slug,
            note=f"QuestionForge {blueprint.recipe}: {blueprint.title}"[:2000],
        )
        write_json(graph.root.parent / "platform-upload.json", uploaded)
        if status >= 400 or not isinstance(uploaded, dict):
            return "rejected-platform-upload", {"upload": uploaded, "status": status}
        challenge_id = str(uploaded.get("id", ""))
        graph.fact(
            "uploaded",
            f"uploaded {challenge_id}",
            data={"status": status, "response": uploaded},
        )
        if not challenge_id:
            return "uploaded-unknown-id", {"upload": uploaded}
        remaining = max(5, int(deadline - time.monotonic()))
        final = api.wait_for_review(challenge_id, min(remaining, 1800))
        graph.fact("review_state", str(final.get("review_status", "")), data=final)
        review_status = str(final.get("review_status", ""))
        if review_status == "approved":
            return "approved", {"check": checked, "upload": uploaded, "final": final}
        if review_status == "rejected":
            return "rejected-review", {"check": checked, "upload": uploaded, "final": final}
        return "uploaded-pending", {"check": checked, "upload": uploaded, "final": final}
