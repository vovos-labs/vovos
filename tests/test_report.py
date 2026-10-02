"""Contract and security tests for the JSON and HTML reports."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from dpdp_kit import paths
from dpdp_kit.engine import Assessment
from dpdp_kit.models import Control, ControlResult, Evidence, Result, Status, TestMethod
from dpdp_kit.profiles import ResolvedProfile
from dpdp_kit.report import DISCLAIMER, build, headline, write_html, write_json

HOSTILE = "<script>alert('xss')</script><img src=x onerror=alert(1)>"
SCHEMA = Draft202012Validator(json.loads(paths.package_schema("report.schema.json").read_text(encoding="utf-8")))


def control(cid: str, severity: str = "high") -> Control:
    return Control(
        id=cid,
        title=f"Title {cid}",
        description="Description long enough.",
        citation={"act": ["Section 6(1)"]},
        severity=severity,
        tags=["base"],
        test_methods=[TestMethod("t", "x")],
        interpretation={"confidence": "medium", "note": "note"},
        review_status="draft",
        since="test",
    )


def assessment(results: list[ControlResult]) -> Assessment:
    now = datetime(2026, 10, 2, tzinfo=timezone.utc)
    profile = ResolvedProfile("base", "Base", chain=["base"])
    return Assessment(profile, results, {"name": HOSTILE, "url": "https://x.example"}, now, now, ["w1"])


def result(status: Status, *, evidence: list[Evidence] | None = None) -> Result:
    return Result(status, f"detail {HOSTILE}", evidence or [], method="t.x", kind="automated")


@pytest.fixture
def every_status() -> Assessment:
    rows = [
        ControlResult(control("T-FAIL-001", "critical"), Status.FAIL, "critical", [result(Status.FAIL)]),
        ControlResult(control("T-REV-001"), Status.REVIEW, "high", [result(Status.ERROR)]),
        ControlResult(control("T-PASS-001"), Status.PASS, "medium", [result(Status.PASS)]),
        ControlResult(control("T-ATT-001"), Status.ATTESTED, "low", [result(Status.ATTESTED)]),
        ControlResult(control("T-NT-001"), Status.NOT_TESTED, "high", [result(Status.NOT_TESTED)]),
        ControlResult(control("T-NA-001"), Status.NA, "high", excluded_reason="documented reason"),
        ControlResult(
            control("T-EV-001"),
            Status.FAIL,
            "low",
            [
                result(
                    Status.FAIL,
                    evidence=[
                        Evidence.json("banner", {"text": HOSTILE}),
                        Evidence.text("raw", HOSTILE),
                        Evidence.reference("ref", HOSTILE),
                        Evidence(kind="screenshot", label="shot", path=Path("evidence/s.png"), sha256="a" * 64),
                    ],
                )
            ],
            override_reason=HOSTILE,
        ),
    ]
    return assessment(rows)


def test_report_matches_published_schema_for_every_status(every_status: Assessment) -> None:
    report = build(every_status)
    assert list(SCHEMA.iter_errors(report)) == []
    assert {c["status"] for c in report["controls"]} == {"fail", "review", "pass", "attested", "not_tested", "n/a"}


def test_summary_counts(every_status: Assessment) -> None:
    summary = build(every_status)["summary"]
    assert summary["controls"] == 7
    assert summary["by_status"]["fail"] == 2
    assert summary["open_gaps_by_severity"] == {"critical": 1, "high": 0, "medium": 0, "low": 1}
    assert summary["methods_run_by_kind"] == {"automated": 5}  # NOT_TESTED methods did not run; N/A has none


def test_headline_never_claims_compliance(every_status: Assessment) -> None:
    text = headline(build(every_status))
    assert text.startswith("2 gap(s) found (1 critical, 1 low)")
    assert "compliant" not in text.lower()


def test_report_carries_disclaimer(every_status: Assessment) -> None:
    report = build(every_status)
    assert report["disclaimer"] == DISCLAIMER
    assert "not a certification" in DISCLAIMER
    assert "not legal advice" in DISCLAIMER


def test_html_escapes_untrusted_content(every_status: Assessment, tmp_path: Path) -> None:
    html = write_html(build(every_status), tmp_path).read_text(encoding="utf-8")
    assert "<script>alert" not in html
    assert "onerror=alert" not in html.replace("&lt;img src=x onerror=alert(1)&gt;", "")
    assert "&lt;script&gt;" in html


def test_html_orders_by_severity_within_group(every_status: Assessment, tmp_path: Path) -> None:
    html = write_html(build(every_status), tmp_path).read_text(encoding="utf-8")
    assert html.index("T-FAIL-001") < html.index("T-EV-001")  # critical before low


def test_html_embeds_screenshot_with_hash(every_status: Assessment, tmp_path: Path) -> None:
    html = write_html(build(every_status), tmp_path).read_text(encoding="utf-8")
    assert 'src="evidence/s.png"' in html
    assert "sha256 aaaaaaaaaaaaaaaa" in html


def test_json_is_utf8_and_round_trips(every_status: Assessment, tmp_path: Path) -> None:
    report = build(every_status)
    report["target"]["name"] = "हिंदी"
    path = write_json(report, tmp_path)
    assert "हिंदी" in path.read_text(encoding="utf-8")
    assert json.loads(path.read_text(encoding="utf-8")) == report


def test_empty_assessment_is_valid(tmp_path: Path) -> None:
    report = build(assessment([]))
    assert list(SCHEMA.iter_errors(report)) == []
    assert headline(report).startswith("0 gap(s) found (none)")
    write_html(report, tmp_path)
