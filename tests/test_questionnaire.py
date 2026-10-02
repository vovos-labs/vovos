from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

from dpdp_kit.catalogue import default_control_dirs, load_controls
from dpdp_kit.context import Context, PrerequisiteMissing
from dpdp_kit.models import Control, Result, Status
from dpdp_kit.plugins.questionnaire import ANSWERS, answers_template, ask, evidence_items, normalise_answer

QUESTION = {"id": "X.q1", "question": "Is it so?", "expect": "yes"}
CONTROLS: list[Control] = list(load_controls(default_control_dirs()).values())


def run_ask(tmp_path: Path, entry: Any, params: dict[str, Any] = QUESTION) -> Result:
    answers = {} if entry is None else {"X.q1": entry}
    return ask(Context(out_dir=tmp_path, answers=answers), params)


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        ({"answer": "yes", "attested_by": "A. Sharma, DPO"}, Status.ATTESTED),
        ({"answer": "YES ", "attested_by": "A. Sharma"}, Status.ATTESTED),
        ({"answer": "yes"}, Status.REVIEW),  # no named person
        ({"answer": "yes", "attested_by": "   "}, Status.REVIEW),
        ({"answer": "no", "attested_by": "x"}, Status.FAIL),
        ({"answer": "partial", "attested_by": "x"}, Status.REVIEW),
        ({"answer": "unknown"}, Status.REVIEW),
        ({"answer": "maybe"}, Status.REVIEW),
        ("yes", Status.REVIEW),  # bare value accepted, still needs attested_by
        (False, Status.FAIL),  # YAML 'no' becomes False
    ],
)
def test_answer_branches(tmp_path: Path, entry: Any, expected: Status) -> None:
    assert run_ask(tmp_path, entry).status is expected


@pytest.mark.parametrize("entry", [None, {"answer": None}, {"answer": ""}, {"note": "no answer key"}])
def test_unanswered_is_not_tested(tmp_path: Path, entry: Any) -> None:
    with pytest.raises(PrerequisiteMissing, match=r"X.q1"):
        run_ask(tmp_path, entry)


def test_expect_no_inverts_the_question(tmp_path: Path) -> None:
    params = {**QUESTION, "expect": "no"}
    assert run_ask(tmp_path, {"answer": "no", "attested_by": "x"}, params).status is Status.ATTESTED
    assert run_ask(tmp_path, {"answer": "yes", "attested_by": "x"}, params).status is Status.FAIL


def test_yaml_booleans_round_trip(tmp_path: Path) -> None:
    entry = yaml.safe_load("answer: yes\nattested_by: someone\ndate: 2026-10-02")
    result = run_ask(tmp_path, entry)
    assert result.status is Status.ATTESTED
    assert "someone on 2026-10-02" in result.detail


def test_attestation_record_and_references_are_evidence(tmp_path: Path) -> None:
    result = run_ask(tmp_path, {"answer": "yes", "attested_by": "A", "evidence": ["doc-1", "https://x.example"]})
    kinds = [(e.kind, e.content) for e in result.evidence]
    assert kinds[0][0] == "json"
    assert kinds[0][1]["attested_by"] == "A"
    assert kinds[1:] == [("reference", "doc-1"), ("reference", "https://x.example")]


def test_single_string_evidence_is_one_reference_not_characters(tmp_path: Path) -> None:
    """Regression: a string was iterated character by character."""
    result = run_ask(tmp_path, {"answer": "yes", "attested_by": "A", "evidence": "JIRA-1234"})
    assert [e.content for e in result.evidence if e.kind == "reference"] == ["JIRA-1234"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(None, []), ("", []), ("a", ["a"]), (["a", "", " ", 3], ["a", "3"]), (("x",), ["x"])],
)
def test_evidence_items(raw: Any, expected: list[str]) -> None:
    assert evidence_items(raw) == expected


@given(st.one_of(st.none(), st.booleans(), st.text(max_size=20), st.integers()))
def test_normalise_answer_is_total_and_lowercase(value: Any) -> None:
    out = normalise_answer(value)
    assert out == out.strip().lower()


# --- template -----------------------------------------------------------------------------------------


def test_template_lists_every_question_once_unanswered() -> None:
    parsed = yaml.safe_load(answers_template(CONTROLS))
    expected = {m.params["id"] for c in CONTROLS for m in c.test_methods if m.key == "questionnaire.ask"}
    assert set(parsed) == expected
    assert all(v["answer"] is None for v in parsed.values())


def test_template_preserves_mapping_and_scalar_answers() -> None:
    existing = {
        "DPDP-CON-004.q1": {"answer": "yes", "attested_by": "A. Sharma", "evidence": "JIRA-1"},
        "DPDP-CON-005.q1": "no",
    }
    parsed = yaml.safe_load(answers_template(CONTROLS, existing))
    assert parsed["DPDP-CON-004.q1"]["attested_by"] == "A. Sharma"
    assert parsed["DPDP-CON-004.q1"]["evidence"] == ["JIRA-1"]
    assert parsed["DPDP-CON-005.q1"]["answer"] == "no"


answer_entries = st.fixed_dictionaries(
    {
        "answer": st.sampled_from([*ANSWERS, None]),
        "attested_by": st.text(alphabet=st.characters(blacklist_categories=("Cs", "Cc")), max_size=30),
        "note": st.text(alphabet=st.characters(blacklist_categories=("Cs", "Cc")), max_size=60),
    }
)


@settings(max_examples=50, deadline=None)  # renders 25 controls per example; timing varies by machine
@given(st.dictionaries(st.sampled_from(["DPDP-CON-004.q1", "DPDP-NOT-001.q1", "DPDP-BRE-001.q1"]), answer_entries))
def test_template_round_trip_is_lossless(existing: dict[str, dict[str, Any]]) -> None:
    first = yaml.safe_load(answers_template(CONTROLS, existing))
    second = yaml.safe_load(answers_template(CONTROLS, first))
    assert first == second, "regenerating the template must be idempotent"
    for qid, entry in existing.items():
        assert first[qid]["answer"] == (entry["answer"] or None)
        assert first[qid]["attested_by"] == entry["attested_by"].strip()
        assert first[qid]["note"] == entry["note"].strip()


def test_unicode_whitespace_in_notes_is_trimmed_consistently() -> None:
    """Regression (found by Hypothesis): a note of '\\xa0' changed on every regeneration."""
    existing = {"DPDP-CON-004.q1": {"answer": "yes", "attested_by": "\xa0A\xa0", "note": "\xa0"}}
    parsed = yaml.safe_load(answers_template(CONTROLS, existing))
    assert parsed["DPDP-CON-004.q1"]["attested_by"] == "A"
    assert parsed["DPDP-CON-004.q1"]["note"] == ""
