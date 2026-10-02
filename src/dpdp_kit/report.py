"""Build the machine-readable report and render it as JSON and HTML."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import __version__, paths
from .catalogue import catalogue_metadata
from .engine import Assessment
from .models import SEVERITIES, ControlResult, Evidence, Result, Status

REPORT_SCHEMA = "dpdp-kit/report/v1"

DISCLAIMER = (
    "This is a self-assessment produced by an open-source tool. It is not legal advice, "
    "not a certification, and not an endorsement by the Data Protection Board of India or "
    "any authority. A PASS means only that the listed check found no gap; it does not "
    "establish compliance. Automated checks have known blind spots, and interpretation "
    "notes reflect community readings of the law that may differ from those of the Board "
    "or the courts. Have the results reviewed by a qualified professional."
)


def _evidence(ev: Evidence) -> dict[str, Any]:
    out: dict[str, Any] = {"kind": ev.kind, "label": ev.label}
    if ev.path is not None:
        out["path"] = ev.path.as_posix()
    if ev.sha256:
        out["sha256"] = ev.sha256
    if ev.content is not None:
        out["content"] = ev.content
    return out


def _method(r: Result) -> dict[str, Any]:
    return {
        "method": r.method,
        "kind": r.kind,
        "status": r.status.value,
        "detail": r.detail,
        "evidence": [_evidence(e) for e in r.evidence],
    }


def _control(cr: ControlResult) -> dict[str, Any]:
    c = cr.control
    out: dict[str, Any] = {
        "id": c.id,
        "title": c.title,
        "description": c.description,
        "citation": c.citation,
        "citation_text": c.citation_text(),
        "severity": cr.severity,
        "catalogue_severity": c.severity,
        "status": cr.status.value,
        "interpretation": c.interpretation,
        "review_status": c.review_status,
        "methods": [_method(m) for m in cr.methods],
    }
    if cr.excluded_reason:
        out["excluded_reason"] = cr.excluded_reason
    if cr.override_reason:
        out["override_reason"] = cr.override_reason
    return out


def build(assessment: Assessment) -> dict[str, Any]:
    results = assessment.results
    by_status = Counter(r.status.value for r in results)
    open_gaps = Counter(r.severity for r in results if r.status is Status.FAIL)
    method_kinds = Counter(m.kind for r in results for m in r.methods if m.status is not Status.NOT_TESTED)
    meta = catalogue_metadata()
    profile = assessment.profile
    return {
        "schema": REPORT_SCHEMA,
        "tool": {"name": "dpdp-kit", "version": __version__},
        "catalogue": {"version": str(meta.get("version")), "status": meta.get("status"), "law": meta.get("law")},
        "generated_at": assessment.finished_at.isoformat(),
        "started_at": assessment.started_at.isoformat(),
        "profile": {
            "id": profile.id,
            "title": profile.title,
            "chain": profile.chain,
            "overlay": str(profile.overlay) if profile.overlay else None,
        },
        "target": assessment.target,
        "summary": {
            "controls": len(results),
            "by_status": {s.value: by_status.get(s.value, 0) for s in Status if s is not Status.ERROR},
            "open_gaps_by_severity": {s: open_gaps.get(s, 0) for s in SEVERITIES},
            "methods_run_by_kind": dict(method_kinds),
        },
        "warnings": assessment.warnings,
        "disclaimer": DISCLAIMER,
        "controls": [_control(r) for r in results],
    }


def headline(report: dict[str, Any]) -> str:
    s = report["summary"]
    gaps = s["open_gaps_by_severity"]
    tested = s["controls"] - s["by_status"]["n/a"] - s["by_status"]["not_tested"]
    gap_text = ", ".join(f"{n} {sev}" for sev, n in gaps.items() if n) or "none"
    return (
        f"{s['by_status']['fail']} gap(s) found ({gap_text}); "
        f"{tested} of {s['controls'] - s['by_status']['n/a']} in-scope controls had at least one result; "
        f"{s['by_status']['review']} need human review; {s['by_status']['not_tested']} not tested."
    )


def write_json(report: dict[str, Any], out_dir: Path) -> Path:
    path = out_dir / "report.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def write_html(report: dict[str, Any], out_dir: Path) -> Path:
    env = Environment(loader=FileSystemLoader(paths.templates_dir()), autoescape=select_autoescape(["html", "j2"]))
    env.filters["tojson_pretty"] = lambda v: json.dumps(v, indent=2, ensure_ascii=False)
    ordered = sorted(report["controls"], key=lambda c: (SEVERITIES.index(c["severity"]), c["id"]))
    html = env.get_template("report.html.j2").render(report=report, ordered=ordered, headline=headline(report))
    path = out_dir / "report.html"
    path.write_text(html, encoding="utf-8")
    return path
