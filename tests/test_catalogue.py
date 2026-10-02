from pathlib import Path

import pytest

from dpdp_kit import paths
from dpdp_kit.catalogue import CatalogueError, catalogue_metadata, default_control_dirs, load_controls, schema_errors
from dpdp_kit.profiles import resolve, select
from dpdp_kit.registry import registry


@pytest.fixture(scope="module")
def controls():
    return load_controls(default_control_dirs())


def test_catalogue_loads_and_validates(controls):
    assert len(controls) >= 20
    assert all(c.id.startswith("DPDP-") for c in controls.values())


def test_catalogue_metadata_valid():
    assert schema_errors(catalogue_metadata(), paths.catalogue_schema("catalogue.schema.json"), "catalogue.yaml") == []


def test_every_test_method_has_a_builtin_check(controls):
    missing = [f"{c.id}: {m.key}" for c in controls.values() for m in c.test_methods if registry.get(m.key) is None]
    assert missing == []


def test_questionnaire_ids_unique_and_prefixed(controls):
    ids = []
    for c in controls.values():
        for m in c.test_methods:
            if m.key == "questionnaire.ask":
                assert m.params["id"].startswith(c.id + "."), m.params["id"]
                ids.append(m.params["id"])
    assert len(ids) == len(set(ids))


def test_contested_controls_explain_themselves(controls):
    for c in controls.values():
        if c.interpretation["confidence"] != "high":
            assert len(c.interpretation["note"]) > 40, f"{c.id} needs an interpretation note"


@pytest.mark.parametrize("profile", sorted(p.stem for p in paths.profiles_dir().glob("*.yaml")))
def test_every_profile_resolves(controls, profile):
    sel = select(controls, resolve(profile))
    assert sel.selected, f"profile {profile} selects nothing"
    assert sel.warnings == []


def test_file_name_must_match_id(tmp_path: Path):
    src = next((paths.catalogue_dir() / "controls").rglob("DPDP-CON-001.yaml"))
    (tmp_path / "WRONG-NAME-001.yaml").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(CatalogueError, match="file name must match"):
        load_controls([tmp_path])


def _copy_control(tmp_path: Path, cid: str = "DPDP-CON-001") -> Path:
    src = next((paths.catalogue_dir() / "controls").rglob(f"{cid}.yaml"))
    dest = tmp_path / src.name
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return dest


def test_invalid_yaml_names_the_file(tmp_path: Path) -> None:
    (tmp_path / "DPDP-X-001.yaml").write_text("id: [unclosed\n", encoding="utf-8")
    with pytest.raises(CatalogueError, match=r"DPDP-X-001\.yaml: invalid YAML"):
        load_controls([tmp_path])


def test_missing_directory_is_reported(tmp_path: Path) -> None:
    with pytest.raises(CatalogueError, match="control directory not found"):
        load_controls([tmp_path / "nope"])


def test_duplicate_ids_across_directories_are_rejected(tmp_path: Path) -> None:
    _copy_control(tmp_path)
    with pytest.raises(CatalogueError, match="duplicate control id DPDP-CON-001"):
        load_controls([*default_control_dirs(), tmp_path])


def test_all_problems_are_reported_together(tmp_path: Path) -> None:
    (tmp_path / "A-B-001.yaml").write_text("id: A-B-001\n", encoding="utf-8")
    (tmp_path / "C-D-001.yaml").write_text("{bad", encoding="utf-8")
    with pytest.raises(CatalogueError) as info:
        load_controls([tmp_path])
    assert "A-B-001.yaml" in str(info.value)
    assert "C-D-001.yaml" in str(info.value)


def test_citation_text_formats_every_source(controls) -> None:  # type: ignore[no-untyped-def]
    text = controls["DPDP-CM-001"].citation_text()
    assert text == "DPDP Act Section 6(7), Section 6(9); DPDP Rules Rule 4; DPDP Rules First Schedule, Part A"


def test_schema_rejects_bad_severity(tmp_path: Path):
    src = next((paths.catalogue_dir() / "controls").rglob("DPDP-CON-001.yaml"))
    (tmp_path / "DPDP-CON-001.yaml").write_text(
        src.read_text(encoding="utf-8").replace("severity: critical", "severity: urgent"), encoding="utf-8"
    )
    with pytest.raises(CatalogueError, match="severity"):
        load_controls([tmp_path])
