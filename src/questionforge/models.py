from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


Category = Literal["web", "pwn"]
Difficulty = Literal["easy", "medium", "hard"]


@dataclass(frozen=True)
class QuestionSpec:
    id: str
    prompt: str
    weight: int = 1
    requires: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "QuestionSpec":
        return cls(
            id=str(raw["id"]),
            prompt=str(raw["prompt"]),
            weight=int(raw.get("weight", 1)),
            requires=tuple(str(x) for x in raw.get("requires", [])),
            skills=tuple(str(x) for x in raw.get("skills", [])),
        )


@dataclass(frozen=True)
class Blueprint:
    slug: str
    title: str
    description: str
    category: Category
    difficulty: Difficulty
    tags: tuple[str, ...]
    recipe: str
    theme: str
    intended: str
    anti_shortcuts: tuple[str, ...]
    questions: tuple[QuestionSpec, ...]
    parameters: dict[str, Any] = field(default_factory=dict)
    estimated_agent_solve_rate: float = 0.12
    rationale: str = ""
    risk: str = ""
    score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Blueprint":
        category = str(raw.get("category", "web")).lower()
        if category not in ("web", "pwn"):
            raise ValueError(f"unsupported category: {category}")
        difficulty = str(raw.get("difficulty", "medium")).lower()
        if difficulty not in ("easy", "medium", "hard"):
            difficulty = "medium"
        questions = tuple(QuestionSpec.from_dict(q) for q in raw.get("questions", []))
        return cls(
            slug=str(raw["slug"]),
            title=str(raw["title"]),
            description=str(raw["description"]),
            category=category,  # type: ignore[arg-type]
            difficulty=difficulty,  # type: ignore[arg-type]
            tags=tuple(str(x) for x in raw.get("tags", [category])),
            recipe=str(raw["recipe"]),
            theme=str(raw.get("theme", "")),
            intended=str(raw.get("intended", "")),
            anti_shortcuts=tuple(str(x) for x in raw.get("anti_shortcuts", [])),
            questions=questions,
            parameters=dict(raw.get("parameters", {})),
            estimated_agent_solve_rate=float(raw.get("estimated_agent_solve_rate", 0.12)),
            rationale=str(raw.get("rationale", "")),
            risk=str(raw.get("risk", "")),
            score=float(raw.get("score", 0.0)),
        )


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    severity: Literal["error", "warning"]
    path: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass
class VerificationReport:
    ok: bool
    issues: list[ValidationIssue] = field(default_factory=list)
    audit_ok: bool | None = None
    audit_output: str = ""
    local_smoke: str = "not-run"
    smoke_output: str = ""

    def add(self, code: str, severity: str, path: str, message: str) -> None:
        self.issues.append(
            ValidationIssue(
                code=code,
                severity=severity,  # type: ignore[arg-type]
                path=path,
                message=message,
            )
        )
        if severity == "error":
            self.ok = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "issues": [i.to_dict() for i in self.issues],
            "audit_ok": self.audit_ok,
            "audit_output": self.audit_output,
            "local_smoke": self.local_smoke,
            "smoke_output": self.smoke_output,
        }


@dataclass(frozen=True)
class RecipeInfo:
    id: str
    title: str
    category: Category
    summary: str
    complexity: int
    default_difficulty: Difficulty
    parameter_keys: tuple[str, ...]


@dataclass
class BuildResult:
    package_dir: str
    files: list[str]
    sha256: str
