# Writing a check or plugin

A **check** is a Python function registered under a key `plugin.check`. A
**plugin** is a module (or package) of checks. Controls refer to checks by key.

```python
from dpdp_kit.context import Context, PrerequisiteMissing
from dpdp_kit.models import Evidence, Result, Status
from dpdp_kit.registry import check


@check("acme.dpa_register", description="Every processor has a signed DPA.")
def dpa_register(ctx: Context, params: dict) -> Result:
    path = params["register"]
    ...
    if missing:
        return Result(Status.FAIL, "2 processors lack a DPA: ...", [Evidence.file("Register", path)])
    return Result(Status.PASS, "All processors have a DPA.", [Evidence.file("Register", path)])
```

## The contract

| Situation | Do this |
|---|---|
| You looked and found no gap | `Result(Status.PASS, ...)`; say what was and was not covered |
| You found a gap | `Result(Status.FAIL, ...)` with evidence |
| You cannot decide | `Result(Status.REVIEW, ...)`; explain what a person should check |
| You cannot run (missing input, tool not installed) | `raise PrerequisiteMissing("...how to fix...")` |
| AI produced the judgement | Use `kind="ai-assisted"` and return `REVIEW`, never `PASS` |

Unexpected exceptions are caught by the engine and reported as `error`, but
handle the cases you can foresee.

## What a check can use

- `ctx.target`: what is being assessed (`url`, `name`, ...); `ctx.require("url")`
  raises `PrerequisiteMissing` if absent.
- `ctx.answers`: the questionnaire answers file.
- `ctx.options`: CLI options such as `browser_channel`.
- `ctx.resource(key, factory)`: compute something once per run and share it
  between checks (web-scan uses this to load the page only once).
- `ctx.write_evidence(name, bytes_or_text)`: save a file under `evidence/`. It is
  hashed automatically when you attach it with `Evidence.file(...)` or `Evidence.screenshot(...)`.
- `params`: from the control's `test_methods[].params`, merged with any overlay override.

## Loading a plugin

- **Local, for one organisation:** put the `.py` file in a directory and pass
  `--plugins-dir that/directory`.
- **Distributed as a package:** declare an entry point so the kit finds it when installed:

  ```toml
  [project.entry-points."dpdp_kit.plugins"]
  acme = "acme_dpdp_checks"
  ```

- **Built into the kit:** add a module under `src/dpdp_kit/plugins/`, import it in
  `plugins/__init__.py`, and add fixtures and tests.

Run `dpdp-kit plugins` to see which checks are registered.

## Web checks

The `web-scan` plugin loads the page once, without interaction, and stores a
`PageSnapshot` (requests, cookies, detected banner, screenshot). New web checks
should read that snapshot through `_snapshot(ctx)` rather than launching another
browser. Checks that need to interact (for example, clicking "Reject" and
watching the network) should use a separate resource key so the first-load
snapshot stays untouched.
