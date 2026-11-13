from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from .models import Blueprint, VerificationReport


REQUIRED = {
    "metadata.yaml",
    "docker-compose.yml",
    "solution/exploit.py",
    "solution/WRITEUP.md",
}


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except (FileNotFoundError, IsADirectoryError):
        return ""


def static_verify(package: Path, blueprint: Blueprint) -> VerificationReport:
    report = VerificationReport(ok=True)
    for rel in sorted(REQUIRED):
        if not (package / rel).is_file():
            report.add("missing_file", "error", rel, "required CTFY package file is missing")
    metadata = _read(package / "metadata.yaml")
    if not re.search(r"(?m)^standard: CTFY-0002/(?:1|2)$", metadata):
        report.add("standard_missing", "error", "metadata.yaml", "must declare a supported CTFY-0002 version")
    if f"category: {blueprint.category}" not in metadata:
        report.add("category_mismatch", "error", "metadata.yaml", "category differs from blueprint")
    if not re.search(r"(?m)^description:\s", metadata):
        report.add("description_missing", "error", "metadata.yaml", "description is required")
    if not re.search(r"(?m)^questions:\s*$", metadata):
        report.add("questions_missing", "error", "metadata.yaml", "questions list is required")
    if re.search(r"(?m)^\s{4}answer:\s", metadata):
        report.add(
            "fixed_answer",
            "error",
            "metadata.yaml",
            "uploads require per-instance minted answers; fixed answer: is refused",
        )
    if "{{" in metadata or "{%" in metadata:
        report.add(
            "template_in_metadata",
            "error",
            "metadata.yaml",
            "description/prompts must not use unsupported template expressions",
        )
    compose = _read(package / "docker-compose.yml")
    for needle, code in (
        ("privileged: true", "privileged"),
        ("external: true", "external_network"),
        ("container_name:", "container_name"),
        ("network_mode: host", "host_network"),
        ("/var/run/docker.sock", "docker_socket"),
    ):
        if needle in compose:
            report.add(code, "error", "docker-compose.yml", f"refused compose pattern: {needle}")
    if compose.count("cpus:") < 2 or compose.count("memory:") < 2:
        report.add("resources_missing", "warning", "docker-compose.yml", "review resource declarations")
    services_text = ""
    for path in (package / "services").rglob("*"):
        if path.is_file() and path.suffix.lower() in {
            ".py",
            ".c",
            ".h",
            ".js",
            ".ts",
            ".go",
            ".rb",
            ".php",
            ".sh",
            ".html",
            ".txt",
        }:
            services_text += "\n" + _read(path)
    if re.search(r"\bFLAG\{", services_text):
        report.add(
            "literal_flag_in_services",
            "error",
            "services",
            "a running service must never contain a literal FLAG{...}",
        )
    for pattern, code, message in (
        (r"https?://(?!127\.0\.0\.1|localhost|[A-Za-z0-9_.-]+:)", "external_runtime_url", "runtime source contains an absolute external URL"),
        (r"\b(?:ignore prior|ignore previous|reveal (?:your )?system prompt)\b", "solver_prompt_injection", "challenge appears to address the solving agent"),
        (r"169\.254\.169\.254|100\.100\.100\.200", "cloud_metadata", "runtime source references a cloud metadata address"),
    ):
        if re.search(pattern, services_text, re.IGNORECASE):
            report.add(code, "error", "services", message)
    exploit = _read(package / "solution/exploit.py")
    if "from ctfy.challenge.exploit import" not in exploit:
        report.add("exploit_contract", "error", "solution/exploit.py", "missing CTFY exploit import")
    if "run_exploit" not in exploit or "__main__" not in exploit:
        report.add("exploit_entrypoint", "error", "solution/exploit.py", "must call run_exploit")
    if re.search(r"/answers|params/answer\.json|ANSWER_", exploit):
        report.add("exploit_reads_answer", "error", "solution/exploit.py", "solution reads a minted answer directly")
    writeup = _read(package / "solution/WRITEUP.md")
    if len(writeup.strip()) < 100:
        report.add("writeup_empty", "error", "solution/WRITEUP.md", "writeup is too short")
    for path in (package / "attachments").rglob("*"):
        if path.is_symlink():
            report.add("attachment_symlink", "error", str(path), "symlinks are never served")
        if path.name.startswith("."):
            report.add("attachment_hidden", "error", str(path), "hidden attachment names are refused")
    return report


def run_ctfy_check(package: Path, report: VerificationReport) -> None:
    ctfy = shutil.which("ctfy")
    if not ctfy:
        report.add(
            "ctfy_unavailable",
            "warning",
            "",
            "ctfy CLI not installed; platform check will run after upload",
        )
        report.audit_ok = None
        return
    if os.name == "nt":
        report.add(
            "ctfy_windows_unsupported",
            "warning",
            "",
            "legal ctfy authoring check is Linux-only; run it in WSL/Docker or let the platform preflight run it",
        )
        report.audit_ok = None
        return
    source = package.resolve()
    result = subprocess.run(
        [ctfy, "authoring", "check", str(source), "--json"],
        cwd=str(source.parent),
        capture_output=True,
        text=True,
        timeout=180,
        env=os.environ.copy(),
    )
    report.audit_output = (result.stdout + "\n" + result.stderr).strip()
    report.audit_ok = result.returncode == 0
    if result.returncode != 0:
        report.add("ctfy_check_failed", "error", "", "ctfy authoring check rejected the package")


def run_local_smoke(package: Path, report: VerificationReport) -> None:
    ctfy = shutil.which("ctfy")
    if not ctfy:
        report.local_smoke = "unavailable"
        return
    if os.name == "nt":
        report.local_smoke = "unsupported-host"
        return
    source = package.resolve()
    result = subprocess.run(
        [ctfy, "authoring", "smoke", str(source), "--local"],
        cwd=str(source.parent),
        capture_output=True,
        text=True,
        timeout=900,
        env=os.environ.copy(),
    )
    report.smoke_output = (result.stdout + "\n" + result.stderr).strip()
    if result.returncode == 0:
        report.local_smoke = "solved"
    elif result.returncode == 1:
        report.local_smoke = "unsolved"
        report.add("local_smoke_unsolved", "error", "", "reference exploit did not capture the answer")
    elif result.returncode == 2:
        report.local_smoke = "estate_failed"
        report.add("local_smoke_estate", "error", "", "challenge or reference image failed to start")
    else:
        report.local_smoke = "malformed"
        report.add("local_smoke_malformed", "error", "", "package could not be read by local smoke")
