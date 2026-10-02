"""Run the selected controls' checks and roll results up per control."""

from __future__ import annotations

import hashlib
import logging
import traceback
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .context import Context, PrerequisiteMissing
from .models import Control, ControlResult, Result, Status, TestMethod
from .profiles import ResolvedProfile, Selection
from .registry import CheckSpec, Registry
from .registry import registry as default_registry

log = logging.getLogger(__name__)


@dataclass
class Assessment:
    profile: ResolvedProfile
    results: list[ControlResult]
    target: dict[str, Any]
    started_at: datetime
    finished_at: datetime
    warnings: list[str] = field(default_factory=list)


def aggregate(statuses: Iterable[Status]) -> Status:
    """Roll method outcomes up to one control outcome.

    FAIL wins. Otherwise an inconclusive or crashed check makes the control
    REVIEW, unless a person has attested it. Then PASS, then ATTESTED.
    """
    s = set(statuses)
    if Status.FAIL in s:
        return Status.FAIL
    if s & {Status.REVIEW, Status.ERROR} and Status.ATTESTED not in s:
        return Status.REVIEW
    if Status.PASS in s:
        return Status.PASS
    if Status.ATTESTED in s:
        return Status.ATTESTED
    return Status.NOT_TESTED


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _finalise_evidence(result: Result, out_dir: Path) -> None:
    """Hash file evidence and make paths inside the report folder relative, so reports are portable.

    Relative paths given by checks are resolved against the working directory, as
    the user would expect from a path in a control's params or on the command line.
    """
    root = out_dir.resolve()
    for ev in result.evidence:
        if ev.path is None:
            continue
        path = ev.path.resolve()
        if not path.is_file():
            log.warning("evidence file %s for %s does not exist", path, result.method)
            continue
        ev.sha256 = sha256_file(path)
        ev.path = path.relative_to(root) if path.is_relative_to(root) else path


def _invoke(spec: CheckSpec, ctx: Context, params: dict[str, Any]) -> Result:
    try:
        # Typed as object: third-party plugins are not type-checked, so verify the contract at runtime.
        result: object = spec.func(ctx, params)
    except PrerequisiteMissing as exc:
        return Result(Status.NOT_TESTED, str(exc))
    except Exception as exc:  # a broken check must not abort the assessment
        log.debug("check %s crashed", spec.key, exc_info=True)
        detail = f"Check crashed: {exc}"
        if ctx.options.get("debug"):
            detail += "\n" + traceback.format_exc()
        return Result(Status.ERROR, detail)
    if not isinstance(result, Result):
        return Result(Status.ERROR, f"Check returned {type(result).__name__}, expected Result (plugin bug).")
    return result


def _run_method(method: TestMethod, override: dict[str, Any], ctx: Context, reg: Registry) -> Result:
    params = {**method.params, **override.get("params", {}).get(method.key, {})}
    spec = reg.get(method.key)
    if spec is None:
        result = Result(Status.NOT_TESTED, f"No installed plugin provides '{method.key}'.")
    else:
        result = _invoke(spec, ctx, params)
    result.method = method.key
    result.kind = spec.kind if spec else "unknown"
    _finalise_evidence(result, ctx.out_dir)
    return result


def run_control(control: Control, ctx: Context, profile: ResolvedProfile, reg: Registry) -> ControlResult:
    override = profile.overrides.get(control.id, {})
    results = [_run_method(m, override, ctx, reg) for m in control.test_methods]
    return ControlResult(
        control=control,
        status=aggregate(r.status for r in results),
        severity=override.get("severity", control.severity),
        methods=results,
        override_reason=override.get("reason"),
    )


def run(selection: Selection, profile: ResolvedProfile, ctx: Context, reg: Registry = default_registry) -> Assessment:
    """Run every selected control and list excluded ones as N/A. Never raises for check failures."""
    started = datetime.now(timezone.utc)
    results = [run_control(c, ctx, profile, reg) for c in selection.selected]
    results += [
        ControlResult(control=c, status=Status.NA, severity=c.severity, excluded_reason=reason)
        for c, reason in selection.excluded
    ]
    results.sort(key=lambda r: r.control.id)
    return Assessment(
        profile=profile,
        results=results,
        target=ctx.target,
        started_at=started,
        finished_at=datetime.now(timezone.utc),
        warnings=list(selection.warnings),
    )
