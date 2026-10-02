"""End-to-end tests of the command-line interface."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from dpdp_kit import paths
from dpdp_kit.cli import EXIT_GAPS, EXIT_OK, EXIT_USAGE, main, questionnaire_id_problems
from dpdp_kit.models import Control, TestMethod

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
ANSWERS = EXAMPLES / "answers.example.yaml"


def report_of(out: Path) -> dict:  # type: ignore[type-arg]
    return json.loads((out / "report.json").read_text(encoding="utf-8"))


def statuses(out: Path) -> dict[str, str]:
    return {c["id"]: c["status"] for c in report_of(out)["controls"]}


# --- validate ---------------------------------------------------------------------------------------


def test_validate_bundled_catalogue_passes(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate"]) == EXIT_OK
    assert "controls, 6 profiles" in capsys.readouterr().out


def test_validate_example_overlay_and_org_controls(capsys: pytest.CaptureFixture[str]) -> None:
    args = ["validate", "--overlay", str(EXAMPLES / "local-overlay.example.yaml")]
    assert main([*args, "--extra-controls", str(EXAMPLES / "org-controls")]) == EXIT_OK
    assert "no installed plugin provides 'acme.dpa_register'" in capsys.readouterr().err  # warning, not error
    plugins = ["--plugins-dir", str(EXAMPLES / "plugins")]
    assert main([*args, "--extra-controls", str(EXAMPLES / "org-controls"), *plugins]) == EXIT_OK


def _question_control(cid: str, qid: str) -> Control:
    return Control(
        cid, "t", "description", {"other": ["x"]}, "low", ["x"],
        [TestMethod("questionnaire", "ask", {"id": qid})], {"confidence": "high", "note": ""}, "draft", "x",
    )  # fmt: skip


def test_questionnaire_id_rules() -> None:
    """Regression: the prefix check referenced an undefined variable and crashed validate."""
    controls = {
        "A-B-001": _question_control("A-B-001", "A-B-001.q1"),
        "A-B-002": _question_control("A-B-002", "WRONG.q1"),
        "A-B-003": _question_control("A-B-003", "A-B-001.q1"),
    }
    problems = questionnaire_id_problems(controls)
    assert "A-B-002: questionnaire id 'WRONG.q1' must start with 'A-B-002.'" in problems
    assert "duplicate questionnaire id 'A-B-001.q1'" in problems


def test_validate_reports_bad_extra_controls(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "ORG-X-001.yaml").write_text("id: ORG-X-001\n", encoding="utf-8")
    assert main(["validate", "--extra-controls", str(tmp_path)]) == EXIT_USAGE
    assert "ORG-X-001.yaml" in capsys.readouterr().out


def test_validate_reports_bad_overlay(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    overlay = tmp_path / "o.yaml"
    overlay.write_text("exclude:\n  DPDP-NOT-003: short\n", encoding="utf-8")
    assert main(["validate", "--overlay", str(overlay)]) == EXIT_USAGE
    assert "o.yaml" in capsys.readouterr().out


# --- list / plugins / questionnaire -----------------------------------------------------------


def test_list_shows_selected_and_excluded(capsys: pytest.CaptureFixture[str]) -> None:
    overlay = str(EXAMPLES / "local-overlay.example.yaml")
    assert main(["list", "--profile", "sdf", "--overlay", overlay, "--plugins-dir", str(EXAMPLES / "plugins")]) == 0
    out = capsys.readouterr().out
    assert "Profile sdf (base -> sdf)" in out
    assert "DPDP-SDF-001" in out
    assert "ACME-POL-001" in out
    assert "DPDP-NOT-003" in out
    assert "[excluded:" in out


def test_plugins_lists_builtin_checks(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["plugins"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "web-scan.pre_consent_trackers" in out
    assert "questionnaire.ask" in out


def test_questionnaire_writes_then_preserves_answers(tmp_path: Path) -> None:
    out = tmp_path / "answers.yaml"
    assert main(["questionnaire", "--profile", "children", "-o", str(out)]) == EXIT_OK
    data = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert "DPDP-CHD-001.q1" in data
    data["DPDP-CHD-001.q1"].update(answer="yes", attested_by="Guardian Officer")
    out.write_text(yaml.safe_dump(data), encoding="utf-8")

    assert main(["questionnaire", "--profile", "children", "-o", str(out)]) == EXIT_OK
    assert yaml.safe_load(out.read_text(encoding="utf-8"))["DPDP-CHD-001.q1"]["attested_by"] == "Guardian Officer"


# --- run --------------------------------------------------------------------------------------------


def test_questionnaire_only_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    args = ["run", "--profile", "sdf", "--answers", str(ANSWERS), "--out", str(tmp_path), "--name", "Example"]
    assert main(args) == EXIT_OK
    result = statuses(tmp_path)
    assert result["DPDP-CON-004"] == "attested"
    assert result["DPDP-BRE-001"] == "fail"
    assert result["DPDP-NOT-002"] == "review"  # partial
    assert result["DPDP-CON-001"] == "not_tested"  # web-only, no --url
    assert (tmp_path / "report.html").is_file()
    assert "gap(s) found" in capsys.readouterr().out


@pytest.mark.parametrize(("threshold", "expected"), [("critical", EXIT_GAPS), ("low", EXIT_GAPS), ("none", EXIT_OK)])
def test_fail_on_threshold(tmp_path: Path, threshold: str, expected: int) -> None:
    args = ["run", "--answers", str(ANSWERS), "--out", str(tmp_path), "--format", "json", "--fail-on", threshold]
    assert main(args) == expected  # DPDP-BRE-001 (critical) is answered "no"


def test_json_only_format_skips_html(tmp_path: Path) -> None:
    assert main(["run", "--out", str(tmp_path), "--format", "json"]) == EXIT_OK
    assert (tmp_path / "report.json").is_file()
    assert not (tmp_path / "report.html").exists()


@pytest.mark.parametrize("fmt", ["pdf", "", "json,xml"])
def test_unknown_format_is_a_usage_error(tmp_path: Path, fmt: str) -> None:
    with pytest.raises(SystemExit) as info:
        main(["run", "--out", str(tmp_path), "--format", fmt])
    assert info.value.code == EXIT_USAGE


def test_negative_settle_time_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        main(["run", "--out", str(tmp_path), "--settle-ms", "-5"])


@pytest.mark.parametrize(
    ("content", "message"),
    [("- just\n- a list\n", "must be a mapping"), ("key: [unclosed\n", "invalid YAML")],
)
def test_malformed_answers_file_is_a_clear_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], content: str, message: str
) -> None:
    answers = tmp_path / "answers.yaml"
    answers.write_text(content, encoding="utf-8")
    assert main(["run", "--answers", str(answers), "--out", str(tmp_path / "out")]) == EXIT_USAGE
    assert message in capsys.readouterr().err


def test_missing_answers_file_is_a_clear_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["run", "--answers", str(tmp_path / "nope.yaml"), "--out", str(tmp_path)]) == EXIT_USAGE
    assert "answers file not found" in capsys.readouterr().err


def test_empty_answers_file_means_nothing_answered(tmp_path: Path) -> None:
    answers = tmp_path / "answers.yaml"
    answers.write_text("", encoding="utf-8")
    assert main(["run", "--answers", str(answers), "--out", str(tmp_path / "o"), "--format", "json"]) == EXIT_OK
    assert set(statuses(tmp_path / "o").values()) == {"not_tested"}


def test_unknown_profile_is_a_usage_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["run", "--profile", "nope", "--out", str(tmp_path)]) == EXIT_USAGE
    assert "Unknown profile 'nope'" in capsys.readouterr().err


def test_example_overlay_and_plugin_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The example plugin's evidence path is relative to the working directory (regression for hashing)."""
    monkeypatch.chdir(ROOT)
    args = [
        "run", "--overlay", str(EXAMPLES / "local-overlay.example.yaml"), "--plugins-dir", str(EXAMPLES / "plugins"),
        "--answers", str(ANSWERS), "--out", str(tmp_path), "--format", "json",
    ]  # fmt: skip
    assert main(args) == EXIT_OK
    report = report_of(tmp_path)
    acme = next(c for c in report["controls"] if c["id"] == "ACME-POL-001")
    assert acme["status"] == "fail"
    assert "Email Sender Inc" in acme["methods"][0]["detail"]
    assert len(acme["methods"][0]["evidence"][0]["sha256"]) == 64
    na = next(c for c in report["controls"] if c["id"] == "DPDP-NOT-003")
    assert na["status"] == "n/a"
    assert "LEG-2026-04" in na["excluded_reason"]
    assert next(c for c in report["controls"] if c["id"] == "DPDP-RET-001")["severity"] == "critical"


def test_broken_plugin_warns_but_run_continues(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    (plugins / "bad.py").write_text("raise ImportError('nope')\n", encoding="utf-8")
    assert main(["run", "--plugins-dir", str(plugins), "--out", str(tmp_path / "o"), "--format", "json"]) == EXIT_OK
    assert "bad.py failed to load" in capsys.readouterr().err


def test_installed_layout_finds_bundled_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The wheel bundles catalogue/ and profiles/ under dpdp_kit/_data; paths must prefer them."""
    pkg = tmp_path / "dpdp_kit"
    shutil.copytree(paths.catalogue_dir(), pkg / "_data" / "catalogue")
    monkeypatch.setattr(paths, "_PKG", pkg)
    assert paths.data_root() == pkg / "_data"


def test_missing_data_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(paths, "_PKG", tmp_path / "a" / "b" / "dpdp_kit")
    with pytest.raises(FileNotFoundError, match="catalogue"):
        paths.data_root()


@pytest.mark.browser
def test_full_run_against_fixture(fixture_server: str, browser_channel: str | None, tmp_path: Path) -> None:
    args = [
        "run", "--url", f"{fixture_server}/noncompliant/", "--out", str(tmp_path),
        "--block-third-party", "--settle-ms", "300", "--fail-on", "high",
    ]  # fmt: skip
    if browser_channel:
        args += ["--browser-channel", browser_channel]
    assert main(args) == EXIT_GAPS
    con001 = next(c for c in report_of(tmp_path)["controls"] if c["id"] == "DPDP-CON-001")
    assert con001["status"] == "fail"
    shots = [e for m in con001["methods"] for e in m["evidence"] if e["kind"] == "screenshot"]
    assert shots
    assert len(shots[0]["sha256"]) == 64
    assert not Path(shots[0]["path"]).is_absolute()


@pytest.mark.browser
def test_non_http_url_is_not_tested(browser_channel: str | None, tmp_path: Path) -> None:
    assert main(["run", "--url", "file:///etc/passwd", "--out", str(tmp_path), "--format", "json"]) == EXIT_OK
    con001 = next(c for c in report_of(tmp_path)["controls"] if c["id"] == "DPDP-CON-001")
    assert con001["status"] == "not_tested"
    assert "http(s)" in con001["methods"][0]["detail"]
