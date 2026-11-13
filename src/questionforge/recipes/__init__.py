from __future__ import annotations

from .ai_tool_agent import AIToolAgentRecipe
from .base import ChallengeRecipe
from .pwn_stack_chain import PwnStackChainRecipe
from .web_object_graph import WebObjectGraphRecipe
from .web_preview_ssrf import WebPreviewSSRFRecipe


RECIPES: dict[str, ChallengeRecipe] = {
    recipe.info.id: recipe
    for recipe in (
        WebPreviewSSRFRecipe(),
        WebObjectGraphRecipe(),
        AIToolAgentRecipe(),
        PwnStackChainRecipe(),
    )
}


def recipe_catalog() -> list[dict[str, object]]:
    variants = {
        "web-preview-ssrf": [
            "guided broker path",
            "topology-to-internal-vault parser mismatch",
            "asset-index routing metadata handoff",
        ],
        "web-object-graph": [
            "single-level linked-object expansion",
            "nested operational graph",
            "deep graph expansion with explicit authorization only at the root",
        ],
        "ai-tool-agent": [
            "guided retrieval-to-tool boundary",
            "indirect workspace injection",
            "two-fragment memory reconstruction",
        ],
        "pwn-stack-chain": [
            "both route addresses leaked",
            "two-frame ret2win with both addresses leaked",
            "master route disclosed only after the first frame",
        ],
    }
    return [
        {
            "id": recipe.info.id,
            "title": recipe.info.title,
            "category": recipe.info.category,
            "summary": recipe.info.summary,
            "complexity": recipe.info.complexity,
            "default_difficulty": recipe.info.default_difficulty,
            "parameters": list(recipe.info.parameter_keys),
            "difficulty_levels": [0, 1, 2],
            "variants": variants.get(recipe.info.id, []),
        }
        for recipe in RECIPES.values()
    ]


__all__ = ["ChallengeRecipe", "RECIPES", "recipe_catalog"]
