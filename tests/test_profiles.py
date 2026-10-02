from pathlib import Path

import pytest

from dpdp_kit.catalogue import CatalogueError, default_control_dirs, load_controls
from dpdp_kit.profiles import resolve, select

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def controls():
    return load_controls(default_control_dirs())


def test_inheritance_adds_tagged_controls(controls):
    base = {c.id for c in select(controls, resolve("base")).selected}
    cm = {c.id for c in select(controls, resolve("consent-manager")).selected}
    assert base < cm
    assert all(cid.startswith("DPDP-CM-") for cid in cm - base)
    assert resolve("consent-manager").chain == ["base", "consent-manager"]


def test_overlay_exclusion_override_and_extra_controls(tmp_path: Path):
    org = tmp_path / "controls"
    org.mkdir()
    (org / "ACME-POL-001.yaml").write_text(
        (ROOT / "examples" / "org-controls" / "ACME-POL-001.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    overlay = tmp_path / "overlay.yaml"
    overlay.write_text(
        """
include:
  ids: ["ACME-*"]
exclude:
  DPDP-NOT-003: "Single-language pilot for internal staff only; legal sign-off ref LEG-42."
overrides:
  DPDP-CON-003:
    severity: medium
    params:
      web-scan.reject_option_first_layer: {require_first_layer_reject: false}
    reason: "Legal opinion LEG-17 reads Section 6(1) as not requiring first-layer reject."
extra_controls: [controls]
""",
        encoding="utf-8",
    )
    profile = resolve("base", overlay)
    controls = load_controls(default_control_dirs() + profile.extra_control_dirs)
    sel = select(controls, profile)
    ids = {c.id for c in sel.selected}
    assert "ACME-POL-001" in ids
    assert "DPDP-NOT-003" not in ids
    assert [c.id for c, _ in sel.excluded] == ["DPDP-NOT-003"]
    assert profile.overrides["DPDP-CON-003"]["params"]["web-scan.reject_option_first_layer"] == {
        "require_first_layer_reject": False
    }


def test_exclusion_requires_a_reason(tmp_path: Path):
    overlay = tmp_path / "overlay.yaml"
    overlay.write_text('exclude:\n  DPDP-NOT-003: ""\n', encoding="utf-8")
    with pytest.raises(CatalogueError):
        resolve("base", overlay)


def test_overlay_cannot_extend(tmp_path: Path):
    overlay = tmp_path / "overlay.yaml"
    overlay.write_text("extends: [sdf]\n", encoding="utf-8")
    with pytest.raises(CatalogueError, match="cannot use 'extends'"):
        resolve("base", overlay)


def test_unknown_profile_lists_available():
    with pytest.raises(CatalogueError, match=r"Available: .*base"):
        resolve("nope")


def test_inheritance_cycle_is_detected(tmp_path: Path):
    a, b = tmp_path / "a.yaml", tmp_path / "b.yaml"
    a.write_text(f"id: a\nextends: ['{b.as_posix()}']\n", encoding="utf-8")
    b.write_text(f"id: b\nextends: ['{a.as_posix()}']\n", encoding="utf-8")
    with pytest.raises(CatalogueError, match="cycle: a -> b -> a"):
        resolve(str(a))


def test_profile_file_needs_an_id(tmp_path: Path):
    path = tmp_path / "anon.yaml"
    path.write_text("include: {tags: [base]}\n", encoding="utf-8")
    with pytest.raises(CatalogueError, match="must declare an 'id'"):
        resolve(str(path))


def test_child_override_params_merge_over_parent(tmp_path: Path):
    overlay = tmp_path / "o.yaml"
    overlay.write_text(
        "overrides:\n  DPDP-CON-001:\n    params:\n      web-scan.pre_consent_trackers: {allow_domains: [x.example]}\n"
        "    reason: 'documented in ticket 42'\n",
        encoding="utf-8",
    )
    profile = resolve("base", overlay)
    assert profile.overrides["DPDP-CON-001"] == {
        "params": {"web-scan.pre_consent_trackers": {"allow_domains": ["x.example"]}},
        "reason": "documented in ticket 42",
    }


def test_typo_in_exclusion_is_warned(controls, tmp_path: Path):
    overlay = tmp_path / "overlay.yaml"
    overlay.write_text('exclude:\n  DPDP-NOT-999: "Does not exist, should be flagged."\n', encoding="utf-8")
    sel = select(controls, resolve("base", overlay))
    assert any("DPDP-NOT-999" in w for w in sel.warnings)
