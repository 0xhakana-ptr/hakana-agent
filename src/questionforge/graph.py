from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .util import atomic_write, exclusive_lock, read_json, utc_now


@dataclass
class Fact:
    id: str
    kind: str
    text: str
    data: dict[str, Any] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)
    creator: str = "agent"


@dataclass
class Intent:
    id: str
    description: str
    from_facts: list[str]
    status: str = "open"
    result_fact: str = ""
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)


class FactGraph:
    """A small per-run fact/intent graph inspired by Sapper's shared memory."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.facts_dir = root / "facts"
        self.intents_dir = root / "intents"
        self.facts_dir.mkdir(parents=True, exist_ok=True)
        self.intents_dir.mkdir(parents=True, exist_ok=True)
        project = self.root / "project.json"
        if not project.exists():
            atomic_write(project, b'{"fact_seq":0,"intent_seq":0,"status":"active","created_at":"' + utc_now().encode() + b'"}')

    def _project(self) -> dict[str, Any]:
        return read_json(self.root / "project.json", {}) or {}

    def _save_project(self, project: dict[str, Any]) -> None:
        atomic_write(
            self.root / "project.json",
            json.dumps(project, ensure_ascii=False, indent=2, sort_keys=True).encode(),
        )

    def fact(
        self,
        kind: str,
        text: str,
        *,
        data: dict[str, Any] | None = None,
        evidence: list[str] | None = None,
        creator: str = "agent",
    ) -> Fact:
        with exclusive_lock(self.root / ".graph.lock"):
            p = self._project()
            p["fact_seq"] = int(p.get("fact_seq", 0)) + 1
            fid = f"f{p['fact_seq']:04d}"
            fact = Fact(fid, kind, text, data or {}, evidence or [], creator=creator)
            atomic_write(
                self.facts_dir / f"{fid}.json",
                json.dumps(asdict(fact), ensure_ascii=False, indent=2).encode(),
            )
            self._save_project(p)
            return fact

    def intent(self, description: str, from_facts: list[str]) -> Intent:
        with exclusive_lock(self.root / ".graph.lock"):
            p = self._project()
            p["intent_seq"] = int(p.get("intent_seq", 0)) + 1
            iid = f"i{p['intent_seq']:04d}"
            intent = Intent(iid, description, from_facts)
            atomic_write(
                self.intents_dir / f"{iid}.json",
                json.dumps(asdict(intent), ensure_ascii=False, indent=2).encode(),
            )
            self._save_project(p)
            return intent

    def claim(self, intent_id: str) -> None:
        self._update_intent(intent_id, status="claimed")

    def done(self, intent_id: str, result_fact: str) -> None:
        self._update_intent(intent_id, status="done", result_fact=result_fact)

    def fail(self, intent_id: str, reason: str) -> Fact:
        fact = self.fact("failure", reason, data={"intent": intent_id})
        self._update_intent(intent_id, status="failed", result_fact=fact.id)
        return fact

    def _update_intent(self, intent_id: str, **updates: str) -> None:
        with exclusive_lock(self.root / ".graph.lock"):
            path = self.intents_dir / f"{intent_id}.json"
            raw = read_json(path)
            if not isinstance(raw, dict):
                raise KeyError(intent_id)
            raw.update(updates)
            raw["updated_at"] = utc_now()
            atomic_write(path, json.dumps(raw, ensure_ascii=False, indent=2).encode())

    def facts(self) -> list[Fact]:
        out: list[Fact] = []
        for path in sorted(self.facts_dir.glob("f*.json")):
            raw = read_json(path)
            if isinstance(raw, dict):
                try:
                    out.append(Fact(**raw))
                except TypeError:
                    continue
        return out

    def intents(self) -> list[Intent]:
        out: list[Intent] = []
        for path in sorted(self.intents_dir.glob("i*.json")):
            raw = read_json(path)
            if isinstance(raw, dict):
                try:
                    out.append(Intent(**raw))
                except TypeError:
                    continue
        return out

    def render(self) -> str:
        lines = ["FACTS"]
        for fact in self.facts():
            lines.append(f"{fact.id} [{fact.kind}] {fact.text}")
        lines.extend(["", "INTENTS"])
        for intent in self.intents():
            lines.append(
                f"{intent.id} [{intent.status}] {intent.description}"
                + (f" -> {intent.result_fact}" if intent.result_fact else "")
            )
        return "\n".join(lines)
