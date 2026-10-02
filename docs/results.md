# How results are produced

## Method results

Each control lists one or more **test methods**. Each method runs one check and
produces one of:

| Status | Produced when |
|---|---|
| `pass` | The check looked and found no gap |
| `fail` | The check found a gap; evidence is attached |
| `review` | The check ran but could not decide (including any AI-assisted output) |
| `attested` | A named person answered the questionnaire as expected |
| `not_tested` | The check could not run: no `--url`, question unanswered, or no plugin installed |
| `error` | The check crashed; run with `--debug` to see the traceback |

## Control result

Method results roll up to one control result, in this order:

1. Any `fail`: the control is **FAIL**.
2. Any `review` or `error`, and nobody attested: **REVIEW**.
3. Any `pass`: **PASS**.
4. Any `attested`: **ATTESTED**.
5. Otherwise: **NOT TESTED**.

Consequences worth knowing:

- An automated failure is never cancelled by an attestation. If the website
  check finds trackers before consent, a "yes" in the questionnaire does not change that.
- An attestation does settle an inconclusive automated check, because a person
  has looked. The report still shows both results.
- Controls excluded by a profile or overlay are reported as **N/A**, with the reason.

## Severity

Each control has a catalogue severity (`critical`, `high`, `medium`, `low`)
reflecting the likely impact on Data Principals and enforcement exposure. An
overlay can change it, with a reason; the report shows both values.

`--fail-on <severity>` makes the CLI exit with code 1 when any FAIL is at or
above that severity, for use in CI pipelines.

## Evidence

File evidence (screenshots, network logs) is saved under `evidence/` next to the
report. Its SHA-256 hash is recorded in `report.json`, so a reviewer can confirm
the files were not changed after the run. References (URLs, document IDs,
tickets) supplied in the questionnaire are recorded as given and not verified.
