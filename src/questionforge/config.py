from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _first_env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.environ.get(name)
        if value is not None:
            return value
    return default


@dataclass(frozen=True)
class AgentConfig:
    platform_url: str
    token: str
    competition_id: str
    model_flavor: str
    model_base_url: str
    model_api_key: str
    model_name: str
    work_dir: Path
    deadline_minutes: int
    dry_run: bool
    upload: bool
    local_smoke: bool
    verbose: bool
    calibration: bool = True
    calibration_trials: int = 5
    calibration_turns: int = 16
    calibration_target: str = ""
    calibration_answers: str = ""
    model_backend: str = "auto"
    claude_bin: str = "claude"
    claude_timeout_s: int = 300

    @classmethod
    def from_env(cls, *, work_dir: str = "", dry_run: bool = False, upload: bool = True) -> "AgentConfig":
        flavor = _first_env("LLM_FLAVOR", default="").lower()
        if flavor not in ("openai", "anthropic"):
            flavor = "openai" if _first_env("OPENAI_API_KEY") else "anthropic"
        base = _first_env(
            "LLM_BASE_URL",
            "OPENAI_BASE_URL" if flavor == "openai" else "ANTHROPIC_BASE_URL",
        )
        api_key = _first_env(
            "LLM_API_KEY",
            "OPENAI_API_KEY" if flavor == "openai" else "ANTHROPIC_AUTH_TOKEN",
            "ANTHROPIC_API_KEY" if flavor == "anthropic" else "",
        )
        model = _first_env(
            "LLM_MODEL",
            "OPENAI_MODEL" if flavor == "openai" else "ANTHROPIC_MODEL",
        )
        root = Path(work_dir or _first_env("AUTHORING_WORK_DIR", "CTFY_WORK_DIR", default="work"))
        minutes = int(_first_env("AUTHORING_DEADLINE_MINUTES", default="540"))
        return cls(
            platform_url=_first_env("CTFY_PLATFORM_URL", "AUTHORING_PLATFORM_URL").rstrip("/"),
            token=_first_env("CTFY_TOKEN", "AUTHORING_TOKEN"),
            competition_id=_first_env(
                "AUTHORING_COMPETITION_ID",
                "CTFY_EVAL_COMPETITION_ID",
                "COMPETITION_ID",
            ),
            model_flavor=flavor,
            model_base_url=base.rstrip("/"),
            model_api_key=api_key,
            model_name=model,
            work_dir=root,
            deadline_minutes=minutes,
            dry_run=dry_run,
            upload=upload and not dry_run,
            local_smoke=os.environ.get("AUTHORING_LOCAL_SMOKE", "0") == "1",
            verbose=os.environ.get("AUTHORING_VERBOSE", "0") == "1",
            calibration=os.environ.get("AUTHORING_CALIBRATION", "1") == "1",
            calibration_trials=max(1, min(20, int(os.environ.get("AUTHORING_CALIBRATION_TRIALS", "5")))),
            calibration_turns=max(3, min(40, int(os.environ.get("AUTHORING_CALIBRATION_TURNS", "16")))),
            calibration_target=_first_env(
                "AUTHORING_CALIBRATION_TARGET",
                "CTFY_TARGET_URL",
            ).rstrip("/"),
            calibration_answers=os.environ.get("AUTHORING_CALIBRATION_ANSWERS", ""),
            model_backend=_first_env("AUTHORING_MODEL_BACKEND", default="auto").lower(),
            claude_bin=_first_env("CLAUDE_BIN", default="claude"),
            claude_timeout_s=max(
                30,
                int(_first_env("CLAUDE_CODE_TIMEOUT", default="300")),
            ),
        )

    def with_overrides(
        self,
        *,
        competition_id: str | None = None,
        work_dir: str | None = None,
        deadline_minutes: int | None = None,
        upload: bool | None = None,
        local_smoke: bool | None = None,
        calibration: bool | None = None,
        calibration_trials: int | None = None,
    ) -> "AgentConfig":
        return AgentConfig(
            platform_url=self.platform_url,
            token=self.token,
            competition_id=self.competition_id if competition_id is None else competition_id,
            model_flavor=self.model_flavor,
            model_base_url=self.model_base_url,
            model_api_key=self.model_api_key,
            model_name=self.model_name,
            work_dir=self.work_dir if work_dir is None else Path(work_dir),
            deadline_minutes=self.deadline_minutes if deadline_minutes is None else deadline_minutes,
            dry_run=self.dry_run,
            upload=self.upload if upload is None else upload,
            local_smoke=self.local_smoke if local_smoke is None else local_smoke,
            verbose=self.verbose,
            calibration=self.calibration if calibration is None else calibration,
            calibration_trials=(
                self.calibration_trials
                if calibration_trials is None
                else max(1, min(20, calibration_trials))
            ),
            calibration_turns=self.calibration_turns,
            calibration_target=self.calibration_target,
            calibration_answers=self.calibration_answers,
            model_backend=self.model_backend,
            claude_bin=self.claude_bin,
            claude_timeout_s=self.claude_timeout_s,
        )
