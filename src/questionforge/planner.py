from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path
from typing import Any

from .llm import ModelClient, ModelUnavailable, generate_candidates
from .models import Blueprint, QuestionSpec
from .recipes import RECIPES, recipe_catalog
from .util import clean_text, clamp, safe_name, slugify


FORBIDDEN_PUBLIC_TERMS = (
    "ssrf",
    "server-side request forgery",
    "prompt injection",
    "ret2win",
    "stack overflow",
    "/answers",
    "answer_",
    "solution:",
)

FORBIDDEN_TAG_TERMS = {
    "ssrf",
    "prompt-injection",
    "ret2win",
    "stack-overflow",
    "idor",
}


def _question_pair() -> tuple[QuestionSpec, QuestionSpec]:
    return (
        QuestionSpec(
            id="checkpoint",
            prompt="Recover the operator's checkpoint.",
            weight=1,
            skills=("cwe:200",),
        ),
        QuestionSpec(
            id="master_key",
            prompt="Use the checkpoint to recover the protected master key.",
            weight=2,
            requires=("checkpoint",),
            skills=("cwe:639",),
        ),
    )


def normalize_blueprint(raw: Blueprint) -> Blueprint:
    recipe = RECIPES.get(raw.recipe)
    if recipe is None:
        raise ValueError(f"unknown recipe: {raw.recipe}")
    if raw.category != recipe.info.category:
        raise ValueError(f"recipe {raw.recipe} belongs to {recipe.info.category}")
    slug = slugify(raw.slug, fallback=slugify(raw.title, recipe.info.id))
    title = safe_name(raw.title, recipe.info.title)
    description = clean_text(raw.description, limit=2400)
    lowered = description.lower()
    if not description or any(term in lowered for term in FORBIDDEN_PUBLIC_TERMS):
        raise ValueError("description exposes a technique or is empty")
    if len(raw.questions) != 2:
        raise ValueError("recipes require exactly two minted questions")
    checkpoint, master = raw.questions
    if checkpoint.id != "checkpoint" or checkpoint.requires:
        raise ValueError("first question must be checkpoint with no prerequisites")
    if master.id != "master_key" or set(master.requires) != {"checkpoint"}:
        raise ValueError("second question must be master_key and require checkpoint")
    if master.weight < checkpoint.weight:
        raise ValueError("master_key weight should not be lower than checkpoint")
    for question in (checkpoint, master):
        prompt = clean_text(question.prompt, limit=700)
        if len(prompt) < 5 or any(term in prompt.lower() for term in FORBIDDEN_PUBLIC_TERMS):
            raise ValueError(f"question {question.id} exposes a technique or is too short")
        if not 1 <= question.weight <= 1000:
            raise ValueError("question weight outside 1..1000")
    checkpoint = replace(checkpoint, prompt=clean_text(checkpoint.prompt, limit=700))
    master = replace(master, prompt=clean_text(master.prompt, limit=700))
    required_tags = [recipe.info.category, "multi-stage"]
    if recipe.info.id == "ai-tool-agent":
        required_tags.append("ai-security")
    tags = tuple(
        dict.fromkeys(
            [
                *(
                    re.sub(r"[^a-z0-9-]+", "-", clean_text(tag, limit=48).lower()).strip("-")
                    for tag in raw.tags
                    if clean_text(tag, limit=48)
                    and clean_text(tag, limit=48).lower() not in FORBIDDEN_TAG_TERMS
                ),
                *required_tags,
            ]
        )
    )[:12]
    tags = tuple(tag for tag in tags if tag)
    intended = clean_text(raw.intended, limit=1800)
    if len(intended) < 30:
        raise ValueError("intended solve path is too short")
    anti = tuple(clean_text(item, limit=240) for item in raw.anti_shortcuts if clean_text(item, limit=240))
    rate = clamp(float(raw.estimated_agent_solve_rate), 0.0, 1.0)
    risk = clean_text(raw.risk, limit=800)
    parameters = dict(raw.parameters)
    try:
        parameters["difficulty_level"] = max(
            0, min(2, int(parameters.get("difficulty_level", 1)))
        )
    except (TypeError, ValueError):
        parameters["difficulty_level"] = 1
    risk_penalty = 16.0 if risk.lower().startswith(("high", "critical")) else 5.0
    score = 40.0 - abs(rate - 0.12) * 180.0 + recipe.info.complexity * 4.0 - risk_penalty
    return replace(
        raw,
        slug=slug,
        title=title,
        description=description,
        tags=tags,
        questions=(checkpoint, master),
        parameters=parameters,
        estimated_agent_solve_rate=rate,
        intended=intended,
        anti_shortcuts=anti,
        rationale=clean_text(raw.rationale, limit=1200),
        risk=risk,
        score=score,
    )


def classify_recipe(theme: str) -> str:
    text = theme.lower()
    if any(
        word in text
        for word in (
            "ai",
            "llm",
            "agent",
            "model",
            "prompt",
            "tool",
            "智能体",
            "模型",
            "提示",
            "工具",
            "记忆",
        )
    ):
        return "ai-tool-agent"
    if any(
        word in text
        for word in (
            "memory",
            "binary",
            "pwn",
            "stack",
            "shell",
            "control",
            "二进制",
            "栈",
            "控制流",
            "漏洞利用",
        )
    ):
        return "pwn-stack-chain"
    if any(
        word in text
        for word in (
            "object graph",
            "linked record",
            "relationship",
            "object ownership",
            "对象图",
            "关系图",
            "关联记录",
            "对象关系",
            "委托权限",
        )
    ):
        return "web-object-graph"
    return "web-preview-ssrf"


def fallback_blueprint(theme: str) -> Blueprint:
    recipe_id = classify_recipe(theme)
    raw = RECIPES[recipe_id].default_blueprint(theme)
    return normalize_blueprint(raw)


def plan(
    *,
    theme: str,
    client: ModelClient | None,
    graph=None,
) -> Blueprint:
    if client is not None and client.available:
        try:
            candidates = generate_candidates(
                client,
                theme=theme,
                recipes=recipe_catalog(),
            )
            normalized: list[Blueprint] = []
            for candidate in candidates:
                try:
                    normalized.append(normalize_blueprint(candidate))
                except ValueError as exc:
                    if graph is not None:
                        graph.fact("discarded_candidate", str(exc), data=candidate.to_dict())
            if normalized:
                chosen = max(normalized, key=lambda item: item.score)
                if graph is not None:
                    for candidate in normalized:
                        graph.fact(
                            "candidate",
                            f"{candidate.title} ({candidate.recipe}) score={candidate.score:.1f}",
                            data=candidate.to_dict(),
                        )
                return chosen
        except (ModelUnavailable, ValueError) as exc:
            if graph is not None:
                graph.fact("model_fallback", f"planner fallback: {exc}")
    return fallback_blueprint(theme)
