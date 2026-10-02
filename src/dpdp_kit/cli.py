"""Command-line interface: dpdp-kit <command>.

User-facing output goes to stdout; warnings and diagnostics go to stderr.
Exit codes: 0 success, 1 gaps at or above --fail-on, 2 invalid input or configuration.
"""

from __future__ import annotations

import argparse
import logging
import sys
import webbrowser
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import __version__, paths
from .catalogue import (
    CatalogueError,
    catalogue_metadata,
    default_control_dirs,
    load_controls,
    load_yaml,
    schema_errors,
)
from .context import Context
from .engine import run as run_engine
from .models import SEVERITIES, Control, Status
from .plugins.questionnaire import answers_template
from .profiles import ResolvedProfile, Selection, resolve, select
from .registry import load_plugins, registry
from .report import build, headline, write_html, write_json

EXIT_OK, EXIT_GAPS, EXIT_USAGE = 0, 1, 2
FORMATS = ("json", "html")
BUILTIN_PLUGINS = ("web-scan", "questionnaire")


@dataclass(frozen=True)
class Loaded:
    profile: ResolvedProfile
    controls: dict[str, Control]
    selection: Selection


def _warn(message: str) -> None:
    print(f"warning: {message}", file=sys.stderr)


def _load(args: argparse.Namespace) -> Loaded:
    for err in load_plugins(args.plugins_dir or []):
        _warn(err)
    overlay = Path(args.overlay) if getattr(args, "overlay", None) else None
    profile = resolve(args.profile, overlay)
    controls = load_controls(default_control_dirs() + profile.extra_control_dirs)
    return Loaded(profile, controls, select(controls, profile))


# --- validate ---------------------------------------------------------------------------------


def plugin_reference_problems(controls: dict[str, Control]) -> tuple[list[str], list[str]]:
    """(errors, warnings) for test methods whose check is not registered.

    Missing built-in checks are errors (a catalogue bug); missing third-party checks are warnings.
    """
    errors: list[str] = []
    warnings: list[str] = []
    for control in controls.values():
        for method in control.test_methods:
            if registry.get(method.key) is None:
                target = errors if method.plugin in BUILTIN_PLUGINS else warnings
                target.append(f"{control.id}: no installed plugin provides '{method.key}'")
    return errors, warnings


def questionnaire_id_problems(controls: dict[str, Control]) -> list[str]:
    """Question ids must be unique and prefixed with their control id, so answers files stay unambiguous."""
    problems: list[str] = []
    seen: Counter[str] = Counter()
    for control in controls.values():
        for method in control.test_methods:
            if method.key != "questionnaire.ask":
                continue
            qid = str(method.params.get("id", ""))
            seen[qid] += 1
            if not qid.startswith(control.id + "."):
                problems.append(f"{control.id}: questionnaire id '{qid}' must start with '{control.id}.'")
    problems += [f"duplicate questionnaire id '{qid}'" for qid, n in sorted(seen.items()) if n > 1]
    return problems


def cmd_validate(args: argparse.Namespace) -> int:
    for err in load_plugins(args.plugins_dir or []):
        _warn(err)
    try:
        controls = load_controls(default_control_dirs() + [Path(d) for d in args.extra_controls or []])
    except CatalogueError as exc:
        print(f"Catalogue errors:\n{exc}")
        return EXIT_USAGE

    problems, warnings = plugin_reference_problems(controls)
    problems += questionnaire_id_problems(controls)
    profile_files = sorted(paths.profiles_dir().glob("*.yaml"))
    for path in profile_files:
        try:
            warnings += select(controls, resolve(path.stem)).warnings
        except CatalogueError as exc:
            problems.append(str(exc))
    if args.overlay:
        try:
            resolve("base", Path(args.overlay))
        except CatalogueError as exc:
            problems.append(str(exc))
    problems += schema_errors(catalogue_metadata(), paths.catalogue_schema("catalogue.schema.json"), "catalogue.yaml")

    for w in warnings:
        _warn(w)
    for p in problems:
        print(f"error: {p}")
    status = "OK" if not problems else f"{len(problems)} error(s)"
    print(f"{len(controls)} controls, {len(profile_files)} profiles, {len(registry.all())} checks: {status}")
    return EXIT_OK if not problems else EXIT_USAGE


# --- list / plugins / questionnaire ------------------------------------------------------------


def cmd_list(args: argparse.Namespace) -> int:
    loaded = _load(args)
    sel = loaded.selection
    print(f"Profile {loaded.profile.id} ({' -> '.join(loaded.profile.chain)}): {len(sel.selected)} controls\n")
    for c in sel.selected:
        methods = ", ".join(m.key for m in c.test_methods)
        print(f"{c.id:<18} {c.severity:<8} {c.title}\n{'':<27} {c.citation_text()} | {methods}")
    for c, reason in sel.excluded:
        print(f"{c.id:<18} n/a      {c.title}  [excluded: {reason}]")
    for w in sel.warnings:
        _warn(w)
    return EXIT_OK


def cmd_plugins(args: argparse.Namespace) -> int:
    for err in load_plugins(args.plugins_dir or []):
        _warn(err)
    for spec in registry.all():
        print(f"{spec.key:<38} {spec.kind:<12} {spec.description}  [{spec.module}]")
    return EXIT_OK


def load_answers(path: Path | None) -> dict[str, Any]:
    """Read an answers file. Raises CatalogueError unless it is a mapping keyed by question id."""
    if path is None or not path.exists():
        if path is not None:
            raise CatalogueError(f"{path}: answers file not found")
        return {}
    data = load_yaml(path)
    if data is None:
        return {}
    if not isinstance(data, dict) or not all(isinstance(k, str) for k in data):
        raise CatalogueError(f"{path}: answers file must be a mapping of question id -> answer")
    return data


def cmd_questionnaire(args: argparse.Namespace) -> int:
    loaded = _load(args)
    out = Path(args.output)
    existing = load_answers(out) if out.is_file() else {}
    out.write_text(answers_template(loaded.selection.selected, existing), encoding="utf-8")
    kept = " (existing answers kept)" if existing else ""
    print(f"Wrote {out}{kept}. Fill it in, then pass it with --answers.")
    return EXIT_OK


# --- run -----------------------------------------------------------------------------------------


def gaps_at_or_above(results: Sequence[Any], threshold: str) -> list[str]:
    """Ids of FAIL controls whose severity is at or above ``threshold`` ('none' disables the gate)."""
    if threshold == "none":
        return []
    limit = SEVERITIES.index(threshold)
    return [r.control.id for r in results if r.status is Status.FAIL and SEVERITIES.index(r.severity) <= limit]


def cmd_run(args: argparse.Namespace) -> int:
    loaded = _load(args)
    answers = load_answers(Path(args.answers) if args.answers else None)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = {k: v for k, v in {"url": args.url, "name": args.name}.items() if v}
    options = {
        "browser_channel": args.browser_channel,
        "settle_ms": args.settle_ms,
        "block_third_party": args.block_third_party,
        "debug": args.debug,
    }
    ctx = Context(out_dir=out_dir, target=target, answers=answers, options=options)
    assessment = run_engine(loaded.selection, loaded.profile, ctx)
    report = build(assessment)
    written = []
    if "json" in args.format:
        written.append(write_json(report, out_dir))
    if "html" in args.format:
        written.append(write_html(report, out_dir))

    print(headline(report))
    for w in report["warnings"]:
        _warn(w)
    for path in written:
        print(f"Wrote {path}")
    if args.open and "html" in args.format:
        webbrowser.open((out_dir / "report.html").resolve().as_uri())

    gaps = gaps_at_or_above(assessment.results, args.fail_on)
    if gaps:
        print(f"{len(gaps)} gap(s) at or above '{args.fail_on}' severity: {', '.join(gaps)}")
        return EXIT_GAPS
    return EXIT_OK


# --- parser --------------------------------------------------------------------------------------


def _formats(value: str) -> frozenset[str]:
    chosen = frozenset(v.strip() for v in value.split(",") if v.strip())
    unknown = chosen - set(FORMATS)
    if not chosen or unknown:
        raise argparse.ArgumentTypeError(f"choose from {','.join(FORMATS)}; got {value!r}")
    return chosen


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be zero or a positive number")
    return number


def _add_common(p: argparse.ArgumentParser, *, profile: bool = True) -> None:
    if profile:
        p.add_argument("--profile", default="base", help="profile name or path to a profile YAML (default: base)")
        p.add_argument("--overlay", help="organisation overlay YAML: exclusions, overrides, extra controls")
    p.add_argument("--plugins-dir", action="append", help="directory of local plugin .py files (repeatable)")


def _add_run(sub: Any) -> None:
    p = sub.add_parser("run", help="run the assessment and write the report")
    _add_common(p)
    p.add_argument("--url", help="website to scan (enables web-scan checks)")
    p.add_argument("--name", help="organisation or system name shown in the report")
    p.add_argument("--answers", help="answers YAML from 'dpdp-kit questionnaire'")
    p.add_argument("--out", default="dpdp-report", help="output directory (default: dpdp-report)")
    p.add_argument("--format", default="json,html", type=_formats, help="comma-separated: json,html")
    p.add_argument(
        "--fail-on",
        default="none",
        choices=["none", *SEVERITIES],
        help="exit 1 if any gap at or above this severity (for CI)",
    )
    p.add_argument("--browser-channel", help="use an installed browser, e.g. chrome or msedge")
    p.add_argument("--settle-ms", type=_positive_int, default=4000, help="wait after page load before inspecting")
    p.add_argument(
        "--block-third-party",
        action="store_true",
        help="record but do not send third-party requests (may hide trackers loaded by other trackers)",
    )
    p.add_argument("--open", action="store_true", help="open the HTML report when done")
    p.add_argument("--debug", action="store_true", help="include tracebacks for crashed checks")
    p.set_defaults(func=cmd_run)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dpdp-kit",
        description="Open-source self-assessment against India's DPDP Act, 2023 and DPDP Rules, 2025. "
        "Produces a gap report, not a certification.",
    )
    parser.add_argument("--version", action="version", version=f"dpdp-kit {__version__}")
    parser.add_argument("-v", "--verbose", action="count", default=0, help="more diagnostics on stderr (-vv for debug)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate", help="validate the catalogue, profiles and plugin references")
    _add_common(p, profile=False)
    p.add_argument("--overlay", help="also validate this overlay")
    p.add_argument("--extra-controls", action="append", help="also validate controls in this directory")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("list", help="list the controls a profile selects")
    _add_common(p)
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("plugins", help="list installed checks")
    _add_common(p, profile=False)
    p.set_defaults(func=cmd_plugins)

    p = sub.add_parser("questionnaire", help="write (or refresh) an answers file for a profile")
    _add_common(p)
    p.add_argument("-o", "--output", default="answers.yaml")
    p.set_defaults(func=cmd_questionnaire)

    _add_run(sub)
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    level = {0: logging.WARNING, 1: logging.INFO}.get(args.verbose, logging.DEBUG)
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s", stream=sys.stderr, force=True)
    try:
        code: int = args.func(args)
    except CatalogueError as exc:
        print(f"error:\n{exc}", file=sys.stderr)
        return EXIT_USAGE
    return code


if __name__ == "__main__":
    sys.exit(main())
