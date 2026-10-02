"""Core data types shared by the engine, plugins and reports."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

SEVERITIES = ("critical", "high", "medium", "low")


class Status(str, Enum):
    """Outcome of a single check (method) or of a whole control.

    PASS        an automated check found no gap
    FAIL        a gap was found, with evidence
    REVIEW      inconclusive; a person must look (includes AI-assisted output)
    ATTESTED    a named person confirmed the requirement via the questionnaire
    NOT_TESTED  nothing could run (no URL given, question unanswered, plugin missing)
    ERROR       method level only: the check crashed; rolls up as REVIEW
    NA          control level only: excluded by a profile or overlay, with a reason
    """

    PASS = "pass"  # noqa: S105 - a result status, not a password
    FAIL = "fail"
    REVIEW = "review"
    ATTESTED = "attested"
    NOT_TESTED = "not_tested"
    ERROR = "error"
    NA = "n/a"


@dataclass(frozen=True)
class TestMethod:
    plugin: str
    check: str
    params: dict[str, Any] = field(default_factory=dict)

    __test__ = False  # not a pytest class

    @property
    def key(self) -> str:
        return f"{self.plugin}.{self.check}"


@dataclass(frozen=True)
class Control:
    id: str
    title: str
    description: str
    citation: dict[str, list[str]]
    severity: str
    tags: list[str]
    test_methods: list[TestMethod]
    interpretation: dict[str, str]
    review_status: str
    since: str
    references: list[dict[str, str]] = field(default_factory=list)
    source: Path | None = None

    @classmethod
    def from_dict(cls, doc: dict[str, Any], source: Path | None = None) -> Control:
        """Build a Control from a schema-validated document."""
        return cls(
            id=doc["id"],
            title=doc["title"],
            description=doc["description"].strip(),
            citation={k: list(v) for k, v in doc["citation"].items()},
            severity=doc["severity"],
            tags=list(doc["tags"]),
            test_methods=[
                TestMethod(m["plugin"], m["check"], dict(m.get("params") or {})) for m in doc["test_methods"]
            ],
            interpretation=dict(doc["interpretation"]),
            review_status=doc["review_status"],
            since=str(doc["since"]),
            references=list(doc.get("references") or []),
            source=source,
        )

    def citation_text(self) -> str:
        labels = {"act": "DPDP Act", "rules": "DPDP Rules", "schedules": "DPDP Rules", "other": "Other:"}
        parts = [f"{labels.get(k, k)} {', '.join(v)}" for k, v in self.citation.items() if v]
        return "; ".join(parts)


@dataclass
class Evidence:
    kind: str  # screenshot | file | json | text | reference
    label: str
    path: Path | None = None
    content: Any = None
    sha256: str | None = None

    @classmethod
    def file(cls, label: str, path: Path | str, kind: str = "file") -> Evidence:
        return cls(kind=kind, label=label, path=Path(path))

    @classmethod
    def screenshot(cls, label: str, path: Path | str) -> Evidence:
        return cls.file(label, path, kind="screenshot")

    @classmethod
    def json(cls, label: str, data: Any) -> Evidence:
        json.dumps(data)  # fail early, in the check that produced it, if not serialisable
        return cls(kind="json", label=label, content=data)

    @classmethod
    def text(cls, label: str, content: str) -> Evidence:
        return cls(kind="text", label=label, content=content)

    @classmethod
    def reference(cls, label: str, target: str) -> Evidence:
        """A pointer to evidence held elsewhere (a URL or internal document ID); not copied or hashed."""
        return cls(kind="reference", label=label, content=target)


@dataclass
class Result:
    status: Status
    detail: str = ""
    evidence: list[Evidence] = field(default_factory=list)
    method: str = ""
    kind: str = ""


@dataclass
class ControlResult:
    control: Control
    status: Status
    severity: str
    methods: list[Result] = field(default_factory=list)
    excluded_reason: str | None = None
    override_reason: str | None = None
