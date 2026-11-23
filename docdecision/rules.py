from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Decision:
    decision: str
    rule: str | None
    reasons: list[str] = field(default_factory=list)
    fields: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "decision": self.decision,
            "rule": self.rule,
            "reasons": self.reasons,
            "fields": self.fields,
        }


COMPARISONS = {
    "lt": lambda a, b: a < b,
    "lte": lambda a, b: a <= b,
    "gt": lambda a, b: a > b,
    "gte": lambda a, b: a >= b,
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "in": lambda a, b: a in b,
    "not_in": lambda a, b: a not in b,
}


@dataclass
class Rule:
    name: str
    when: dict
    suggest: str
    reasons: list[str] = field(default_factory=list)
    priority: int = 100

    @classmethod
    def from_dict(cls, raw: dict) -> "Rule":
        missing = {"name", "when", "suggest"} - set(raw)
        if missing:
            raise ValueError(f"rule missing required keys: {sorted(missing)}")
        return cls(
            name=str(raw["name"]),
            when=dict(raw["when"]),
            suggest=str(raw["suggest"]),
            reasons=[str(r) for r in raw.get("reasons", [])],
            priority=int(raw.get("priority", 100)),
        )

    def matches(self, fields: dict) -> bool:
        for key, condition in self.when.items():
            if key == "any_of":
                if not self._any_of_holds(condition, fields):
                    return False
            elif not self._condition_holds(fields.get(key), condition):
                return False
        return True

    def _any_of_holds(self, groups, fields: dict) -> bool:
        if not isinstance(groups, list) or not groups:
            raise ValueError("any_of must be a non-empty list")
        for group in groups:
            if not isinstance(group, dict):
                raise ValueError("any_of entries must be mappings")
            if all(
                self._condition_holds(fields.get(key), cond)
                for key, cond in group.items()
            ):
                return True
        return False

    def _condition_holds(self, value, condition) -> bool:
        if isinstance(condition, dict):
            for op, expected in condition.items():
                if not self._apply(op, value, expected):
                    return False
            return True
        return self._apply("eq", value, condition)

    def _apply(self, op, value, expected):
        if op == "missing":
            return value is None
        if op == "present":
            return value is not None
        if op == "regex":
            if value is None:
                return False
            return re.search(str(expected), str(value), flags=re.IGNORECASE) is not None
        if op == "eq" and isinstance(value, str) and isinstance(expected, str):
            return value.lower() == expected.lower()
        if op in COMPARISONS:
            if op in ("in", "not_in") and value is None:
                return op == "not_in"
            try:
                return COMPARISONS[op](value, expected)
            except TypeError:
                return False
        raise ValueError(f"unknown operator: {op}")


class RuleEngine:
    def __init__(self, rules: list[Rule], default: str = "needs_review"):
        self.rules = sorted(rules, key=lambda r: (r.priority, r.name))
        self.default = default

    def decide(self, fields: dict) -> Decision:
        for rule in self.rules:
            if rule.matches(fields):
                return Decision(
                    decision=rule.suggest,
                    rule=rule.name,
                    reasons=list(rule.reasons),
                    fields=dict(fields),
                )
        return Decision(
            decision=self.default,
            rule=None,
            reasons=["no rule matched"],
            fields=dict(fields),
        )


def load_engine(path: Path) -> RuleEngine:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw_rules = data.get("rules", [])
    if not isinstance(raw_rules, list):
        raise ValueError("rules must be a list")
    return RuleEngine(rules=[Rule.from_dict(r) for r in raw_rules], default=str(data.get("default", "needs_review")))
