from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..models import Blueprint, BuildResult, RecipeInfo


class ChallengeRecipe(ABC):
    info: RecipeInfo

    @abstractmethod
    def build(self, blueprint: Blueprint, destination: Path) -> BuildResult:
        raise NotImplementedError

    @abstractmethod
    def default_blueprint(self, theme: str) -> Blueprint:
        raise NotImplementedError
