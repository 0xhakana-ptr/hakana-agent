from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .config import AgentConfig


class ClaudeCliUnavailable(RuntimeError):
    pass


class ClaudeCliError(RuntimeError):
    pass


def claude_binary(config: AgentConfig) -> str:
    found = shutil.which(config.claude_bin)
    if not found:
        raise ClaudeCliUnavailable(f"Claude Code CLI not found: {config.claude_bin}")
    return found


def available(config: AgentConfig) -> bool:
    has_key = bool(
        config.model_api_key
        or os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("ANTHROPIC_AUTH_TOKEN")
    )
    return shutil.which(config.claude_bin) is not None and has_key


def version(config: AgentConfig) -> str:
    try:
        binary = claude_binary(config)
        result = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return (result.stdout or result.stderr).strip()
    except (ClaudeCliUnavailable, OSError, subprocess.TimeoutExpired):
        return ""


def call_claude(
    config: AgentConfig,
    *,
    run_dir: Path,
    system: str,
    prompt: str,
    max_tokens: int,
    effort: str = "high",
) -> tuple[str, dict[str, Any]]:
    """Run headless Claude Code with all tools and persistence disabled."""
    binary = claude_binary(config)
    home = run_dir / "claude" / "home"
    sandbox = run_dir / "claude" / "sandbox"
    home.mkdir(parents=True, exist_ok=True)
    sandbox.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["HOME"] = str(home)
    env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
    env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = str(max_tokens)
    if config.model_base_url:
        env.setdefault("ANTHROPIC_BASE_URL", config.model_base_url)
    if config.model_api_key:
        env.setdefault("ANTHROPIC_API_KEY", config.model_api_key)
        env.setdefault("ANTHROPIC_AUTH_TOKEN", config.model_api_key)
    if config.model_name:
        env.setdefault("ANTHROPIC_MODEL", config.model_name)

    command = [
        binary,
        "-p",
        "--output-format",
        "json",
        "--bare",
        "--restricted",
        "--tools",
        "",
        "--permission-mode",
        "dontAsk",
        "--permission-prompts",
        "none",
        "--no-session-persistence",
        "--append-system-prompt",
        system,
    ]
    if config.model_name:
        command.extend(["--model", config.model_name])
    if effort in {"low", "medium", "high", "xhigh", "max"}:
        command.extend(["--effort", effort])

    result = subprocess.run(
        command,
        input=prompt,
        cwd=sandbox,
        env=env,
        text=True,
        capture_output=True,
        timeout=config.claude_timeout_s,
    )
    stderr = result.stderr.strip()
    stdout = result.stdout.strip()
    payload: dict[str, Any] = {}
    if stdout:
        try:
            parsed = json.loads(stdout)
            if isinstance(parsed, dict):
                payload = parsed
        except json.JSONDecodeError:
            payload = {}
    if result.returncode != 0 or payload.get("is_error"):
        raise ClaudeCliError(
            (stderr or str(payload.get("result") or stdout or "Claude Code call failed"))[:2000]
        )
    text = payload.get("result")
    if not isinstance(text, str) or not text.strip():
        text = stdout
    if not text.strip():
        raise ClaudeCliError("Claude Code returned an empty response")
    return text.strip(), {
        "version": "claude-code-2.1.323",
        "model": config.model_name,
        "effort": effort,
        "usage": payload.get("usage"),
        "cost_usd": payload.get("total_cost_usd"),
        "session_id": payload.get("session_id", ""),
    }
