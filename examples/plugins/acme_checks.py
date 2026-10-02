"""Example local plugin. Load it with:  dpdp-kit run ... --plugins-dir examples/plugins

A plugin is any Python module that registers checks with @check. To distribute
one as a package, expose the module under the "dpdp_kit.plugins" entry-point
group in your pyproject.toml instead.
"""

import csv
from pathlib import Path

from dpdp_kit.context import PrerequisiteMissing
from dpdp_kit.models import Evidence, Result, Status
from dpdp_kit.registry import check


@check(
    "acme.dpa_register", description="Every vendor processing personal data has a signed DPA in the vendor register."
)
def dpa_register(ctx, params):
    path = Path(params["register"])
    if not path.is_file():
        raise PrerequisiteMissing(f"vendor register not found at {path}")
    with path.open(newline="", encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r["processes_personal_data"].strip().lower() == "yes"]
    missing = [r["vendor"] for r in rows if r["dpa_signed"].strip().lower() != "yes"]
    evidence = [Evidence.file("Vendor register", path)]
    if missing:
        return Result(
            Status.FAIL, f"{len(missing)} of {len(rows)} processors lack a signed DPA: {', '.join(missing)}.", evidence
        )
    return Result(Status.PASS, f"All {len(rows)} processors have a signed DPA.", evidence)
