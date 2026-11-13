from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import Blueprint, VerificationReport
from .util import utc_now, write_json, write_text


def write_reports(
    run_dir: Path,
    *,
    blueprint: Blueprint,
    package_dir: Path,
    archive: bytes,
    report: VerificationReport,
    model_review: dict[str, Any] | None,
    calibration: dict[str, Any] | None,
    platform_result: dict[str, Any] | None,
    status: str,
) -> None:
    data = {
        "status": status,
        "generated_at": utc_now(),
        "blueprint": blueprint.to_dict(),
        "package_dir": str(package_dir),
        "package_bytes": len(archive),
        "verification": report.to_dict(),
        "model_review": model_review,
        "calibration": calibration,
        "platform_result": platform_result,
    }
    write_json(run_dir / "result.json", data)
    lines = [
        f"# QuestionForge run: {blueprint.title}",
        "",
        f"- Status: **{status}**",
        f"- Recipe: `{blueprint.recipe}`",
        f"- Category: `{blueprint.category}`",
        f"- Difficulty: `{blueprint.difficulty}`",
        f"- Estimated AI-agent full-solve rate: `{blueprint.estimated_agent_solve_rate:.1%}`",
        f"- Package: `{package_dir}`",
        f"- Archive bytes: `{len(archive)}`",
        f"- Static verification: `{'pass' if report.ok else 'fail'}`",
        f"- Official/local audit: `{report.audit_ok}`",
        f"- Local smoke: `{report.local_smoke}`",
        "",
        "## Theme",
        "",
        blueprint.theme,
        "",
        "## Player brief",
        "",
        blueprint.description,
        "",
        "## Intended path (secret)",
        "",
        blueprint.intended,
        "",
        "## Verification issues",
        "",
    ]
    if report.issues:
        lines.extend(
            f"- `{issue.code}` ({issue.severity}) `{issue.path}`: {issue.message}"
            for issue in report.issues
        )
    else:
        lines.append("- None.")
    if model_review:
        lines.extend(
            [
                "",
                "## Adversarial review",
                "",
                f"- Verdict: `{model_review.get('verdict', 'unknown')}`",
                f"- Severity: `{model_review.get('severity', 'unknown')}`",
                f"- Estimated solve rate: `{model_review.get('estimated_solve_rate', 'unknown')}`",
            ]
        )
        for finding in model_review.get("findings", []) or []:
            lines.append(
                f"- `{finding.get('kind', 'other')}` `{finding.get('path', '')}`: "
                f"{finding.get('detail', '')}"
            )
    if calibration:
        lines.extend(
            [
                "",
                "## Difficulty calibration",
                "",
                f"- Source: `{calibration.get('source', 'unknown')}`",
                f"- Attempts: `{calibration.get('trials', 0)}`",
                f"- Full solves: `{calibration.get('solves', 0)}`",
                f"- Measured rate: `{float(calibration.get('solve_rate', 0)):.1%}`",
                f"- Status: `{calibration.get('status', 'unknown')}`",
                f"- Difficulty level: `{calibration.get('current_difficulty_level', 'unknown')}`",
                f"- Suggested level: `{calibration.get('suggested_difficulty_level', 'unknown')}`",
            ]
        )
    if platform_result:
        lines.extend(["", "## Platform", "", "```json", json.dumps(platform_result, indent=2, ensure_ascii=False), "```"])
    write_text(run_dir / "RUN_REPORT.md", "\n".join(lines) + "\n")
