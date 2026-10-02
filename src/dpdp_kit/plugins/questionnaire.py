"""Questionnaire plugin: requirements that need a person to confirm them.

Answers live in a YAML file keyed by question id::

    DPDP-CON-004.q1:
      answer: yes            # yes | no | partial | unknown
      attested_by: "A. Sharma, DPO"
      date: 2026-10-02
      evidence: ["policy/withdrawal-flow.pdf", "JIRA-1234"]
      note: "Withdraw link in footer and account settings"

A bare value (``DPDP-CON-004.q1: yes``) is accepted as the answer alone.
"""

from __future__ import annotations

import textwrap
from collections.abc import Iterable
from typing import Any

import yaml

from ..context import Context, PrerequisiteMissing
from ..models import Control, Evidence, Result, Status
from ..registry import check

ANSWERS = ("yes", "no", "partial", "unknown")


def normalise_answer(value: Any) -> str:
    """Map a raw YAML answer to a lower-case string. YAML 1.1 turns bare yes/no into booleans."""
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "" if value is None else str(value).strip().lower()


def as_entry(raw: Any) -> dict[str, Any]:
    """Accept either a mapping or a bare answer value."""
    return dict(raw) if isinstance(raw, dict) else {"answer": raw}


def clean_text(value: Any) -> str:
    """Free-text field as a trimmed string. Trimming includes Unicode spaces such as NBSP,
    which YAML would otherwise not round-trip faithfully."""
    return "" if value is None else str(value).strip()


def evidence_items(raw: Any) -> list[str]:
    """Accept a list of references or a single reference string."""
    items = raw if isinstance(raw, (list, tuple)) else [raw]
    return [text for text in (clean_text(item) for item in items) if text]


def _evidence(entry: dict[str, Any], answer: str) -> list[Evidence]:
    record = {k: clean_text(entry.get(k)) for k in ("attested_by", "date", "note")}
    record = {k: v for k, v in record.items() if v}
    record["answer"] = answer
    attestation = [Evidence.json("Attestation record", record)]
    return attestation + [
        Evidence.reference("Supporting evidence", ref) for ref in evidence_items(entry.get("evidence"))
    ]


@check(
    "questionnaire.ask",
    kind="attestation",
    description="Ask a person to confirm a requirement and record who attested it.",
)
def ask(ctx: Context, params: dict[str, Any]) -> Result:
    qid = params["id"]
    expect = params.get("expect", "yes")
    question = params.get("question", "").strip()
    entry = as_entry(ctx.answers.get(qid))
    answer = normalise_answer(entry.get("answer"))
    if not answer:
        raise PrerequisiteMissing(f"question {qid} is not answered in the answers file")
    evidence = _evidence(entry, answer)

    if answer not in ANSWERS:
        return Result(Status.REVIEW, f"Unrecognised answer '{answer}' (use {', '.join(ANSWERS)}): {question}", evidence)
    if answer == expect:
        who = clean_text(entry.get("attested_by"))
        if not who:
            return Result(
                Status.REVIEW,
                f"Answered '{answer}' but no 'attested_by' given; an attestation needs a named person.",
                evidence,
            )
        when = f" on {entry['date']}" if entry.get("date") else ""
        return Result(Status.ATTESTED, f"{who}{when}: {answer}. {question}", evidence)
    if answer in ("yes", "no"):
        return Result(Status.FAIL, f"Answered '{answer}' (expected '{expect}'): {question}", evidence)
    return Result(Status.REVIEW, f"Answered '{answer}': {question}", evidence)


def questions(controls: Iterable[Control]) -> list[tuple[Control, dict[str, Any]]]:
    return [(c, m.params) for c in controls for m in c.test_methods if m.key == "questionnaire.ask"]


def _comment(text: str) -> list[str]:
    return [f"# {chunk}" for chunk in textwrap.wrap(text, 96)]


def answers_template(controls: Iterable[Control], existing: dict[str, Any] | None = None) -> str:
    """Render a commented YAML answers file for ``controls``, keeping answers already in ``existing``."""
    existing = existing or {}
    lines = [
        "# DPDP self-test questionnaire",
        "# answer: yes | no | partial | unknown   (leave empty if not yet answered)",
        "# attested_by is required for an answer to count as ATTESTED.",
        "# evidence: list of document paths, URLs or ticket IDs; they are referenced, not uploaded.",
        "",
    ]
    for control, params in questions(controls):
        qid = params["id"]
        prior = as_entry(existing.get(qid))
        lines.append(f"# [{control.id}] {control.title}  ({control.citation_text()})")
        lines += _comment(f"Q: {' '.join(params['question'].split())}")
        if params.get("help"):
            lines += _comment(f"Help: {' '.join(params['help'].split())}")
        block = {
            qid: {
                "answer": normalise_answer(prior.get("answer")) or None,
                "attested_by": clean_text(prior.get("attested_by")),
                "date": clean_text(prior.get("date")),
                "evidence": evidence_items(prior.get("evidence")),
                "note": clean_text(prior.get("note")),
            }
        }
        lines += [yaml.safe_dump(block, sort_keys=False, allow_unicode=True).rstrip(), ""]
    return "\n".join(lines)
