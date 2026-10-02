from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from dpdp_kit.context import Context
from dpdp_kit.engine import aggregate, run, run_control, sha256_file
from dpdp_kit.models import Control, Evidence, Result, Status, TestMethod
from dpdp_kit.profiles import ResolvedProfile, Selection
from dpdp_kit.registry import Registry

S = Status
METHOD_STATUSES = [S.PASS, S.FAIL, S.REVIEW, S.ATTESTED, S.NOT_TESTED, S.ERROR]


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        ([], S.NOT_TESTED),
        ([S.NOT_TESTED], S.NOT_TESTED),
        ([S.PASS, S.NOT_TESTED], S.PASS),
        ([S.PASS, S.FAIL], S.FAIL),
        ([S.ATTESTED, S.FAIL], S.FAIL),
        ([S.PASS, S.REVIEW], S.REVIEW),
        ([S.PASS, S.ERROR], S.REVIEW),
        ([S.REVIEW, S.ATTESTED], S.ATTESTED),
        ([S.PASS, S.ATTESTED], S.PASS),
        ([S.ATTESTED, S.NOT_TESTED], S.ATTESTED),
    ],
)
def test_aggregate_truth_table(statuses: list[Status], expected: Status) -> None:
    assert aggregate(statuses) is expected


@given(st.lists(st.sampled_from(METHOD_STATUSES), max_size=8))
def test_aggregate_properties(statuses: list[Status]) -> None:
    result = aggregate(statuses)
    assert result is aggregate(reversed(statuses)), "order must not matter"
    assert (result is S.FAIL) == (S.FAIL in statuses), "an automated failure is never cancelled"
    assert result in {S.PASS, S.FAIL, S.REVIEW, S.ATTESTED, S.NOT_TESTED}
    if result is S.PASS:
        assert S.PASS in statuses


def make_control(*keys: str, cid: str = "TEST-ENG-001") -> Control:
    return Control(
        id=cid,
        title="Engine test control",
        description="A control used only by the engine tests.",
        citation={"other": ["test"]},
        severity="high",
        tags=["test"],
        test_methods=[TestMethod(*k.split("."), {"x": 1}) for k in keys],
        interpretation={"confidence": "high", "note": ""},
        review_status="draft",
        since="test",
    )


@pytest.fixture
def reg() -> Registry:
    registry = Registry()

    @registry.check("t.ok")
    def ok(ctx: Context, params: dict[str, Any]) -> Result:
        return Result(S.PASS, f"x={params['x']}")

    @registry.check("t.needs_url")
    def needs_url(ctx: Context, params: dict[str, Any]) -> Result:
        ctx.require("url")
        return Result(S.PASS)

    @registry.check("t.crash")
    def crash(ctx: Context, params: dict[str, Any]) -> Result:
        raise RuntimeError("boom")

    @registry.check("t.wrong_type")
    def wrong_type(ctx: Context, params: dict[str, Any]) -> Result:
        return "pass"  # type: ignore[return-value]  # simulates an untyped third-party plugin

    return registry


PROFILE = ResolvedProfile("p", "p")


def test_each_failure_mode_maps_to_its_status(reg: Registry, tmp_path: Path) -> None:
    keys = ("t.ok", "t.needs_url", "t.crash", "t.wrong_type", "t.missing")
    cr = run_control(make_control(*keys), Context(out_dir=tmp_path), PROFILE, reg)

    by_method = {r.method: r for r in cr.methods}
    assert by_method["t.ok"].status is S.PASS
    assert by_method["t.needs_url"].status is S.NOT_TESTED
    assert "--url" in by_method["t.needs_url"].detail
    assert by_method["t.crash"].status is S.ERROR
    assert "boom" in by_method["t.crash"].detail
    assert "Traceback" not in by_method["t.crash"].detail
    assert by_method["t.wrong_type"].status is S.ERROR
    assert by_method["t.missing"].status is S.NOT_TESTED
    assert by_method["t.missing"].kind == "unknown"
    assert cr.status is S.REVIEW


def test_debug_option_includes_traceback(reg: Registry, tmp_path: Path) -> None:
    cr = run_control(make_control("t.crash"), Context(out_dir=tmp_path, options={"debug": True}), PROFILE, reg)
    assert "Traceback" in cr.methods[0].detail


def test_profile_override_merges_params_and_severity(reg: Registry, tmp_path: Path) -> None:
    profile = ResolvedProfile(
        "p", "p", overrides={"TEST-ENG-001": {"severity": "low", "reason": "documented", "params": {"t.ok": {"x": 2}}}}
    )
    cr = run_control(make_control("t.ok"), Context(out_dir=tmp_path), profile, reg)
    assert cr.severity == "low"
    assert cr.override_reason == "documented"
    assert cr.methods[0].detail == "x=2"


# --- evidence finalisation (regression: relative paths outside the report folder lost their hash) ---


def _evidence_check(reg: Registry, path: Path | str) -> None:
    @reg.check("t.evidence")
    def evidence(ctx: Context, params: dict[str, Any]) -> Result:
        return Result(S.PASS, "", [Evidence.file("file", path)])


def test_evidence_inside_report_folder_is_relative_and_hashed(tmp_path: Path) -> None:
    reg = Registry()
    ctx = Context(out_dir=tmp_path)
    written = ctx.write_evidence("shot.png", b"\x89PNG")
    _evidence_check(reg, written)
    ev = run_control(make_control("t.evidence"), ctx, PROFILE, reg).methods[0].evidence[0]
    assert ev.path == Path("evidence/shot.png")
    assert ev.sha256 == sha256_file(written)


def test_relative_evidence_outside_report_folder_resolves_from_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "vendors.csv").write_text("a,b\n", encoding="utf-8")
    monkeypatch.chdir(project)
    reg = Registry()
    _evidence_check(reg, "vendors.csv")
    ev = (
        run_control(make_control("t.evidence"), Context(out_dir=tmp_path / "report"), PROFILE, reg)
        .methods[0]
        .evidence[0]
    )
    assert ev.path == (project / "vendors.csv").resolve()
    assert ev.sha256 is not None


def test_missing_evidence_file_is_logged_not_hashed(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    reg = Registry()
    _evidence_check(reg, tmp_path / "nope.txt")
    ev = run_control(make_control("t.evidence"), Context(out_dir=tmp_path), PROFILE, reg).methods[0].evidence[0]
    assert ev.sha256 is None
    assert "does not exist" in caplog.text


def test_run_reports_excluded_controls_as_na_sorted(reg: Registry, tmp_path: Path) -> None:
    included, excluded = make_control("t.ok", cid="TEST-B-001"), make_control("t.ok", cid="TEST-A-001")
    selection = Selection([included], [(excluded, "documented reason")], ["a warning"])
    assessment = run(selection, PROFILE, Context(out_dir=tmp_path, target={"name": "X"}), reg)
    assert [(r.control.id, r.status) for r in assessment.results] == [("TEST-A-001", S.NA), ("TEST-B-001", S.PASS)]
    assert assessment.results[0].excluded_reason == "documented reason"
    assert assessment.warnings == ["a warning"]
    assert assessment.started_at <= assessment.finished_at
