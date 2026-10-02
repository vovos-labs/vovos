# Governance

The kit is only useful if people trust that it is neutral. These rules exist to
earn and keep that trust.

## Principles

1. **Self-assessment only.** The project does not run a hosted scoring service,
   publish rankings, issue badges, or describe any result as a certification.
2. **Transparent rules.** Every control, threshold and interpretation is a public
   file with a public history. Nothing is decided in private channels.
3. **Disagreement is recorded, not hidden.** Where credible readings of the law
   differ, the control is marked `contested`, the note explains the readings, and
   organisations can override it with a documented reason.
4. **No vendor advantage.** No product, Consent Manager or consultancy receives
   special treatment in controls, checks, fixtures or documentation. Vendor names
   appear only where a check must recognise them (for example, tracker hosts).
5. **Local and private.** The kit collects no telemetry and sends no data except
   the requests needed to load the target website.

## Roles

- **Contributors**: anyone who opens an issue or pull request.
- **Maintainers**: review and merge changes. Listed in `MAINTAINERS.md`
  (to be created when the first external maintainer joins).
- **Legal reviewers**: maintainers or invited contributors with recognised
  expertise in Indian data-protection law. They alone can move a control from
  `review_status: draft` to `legal-reviewed`.

The project aims to have maintainers from **at least three unrelated
organisations** within its first year. Until then, decisions about the meaning of
a control need public sign-off from a legal reviewer who is not employed by the
maintainer's organisation.

## Conflicts of interest

Maintainers and legal reviewers declare commercial interests (for example,
building or selling consent-management, compliance or audit products or
services) in `MAINTAINERS.md`. A person with a conflict on a specific change
discloses it in the pull request, and that change needs approval from a
maintainer without the conflict.

## Changing what a control means

Changes that alter what a control requires, its severity, or its interpretation
go through an **Interpretation RFC**:

1. Open an issue using the *Interpretation RFC* template, citing the legal text
   and any Board guidance, orders or credible commentary.
2. The issue is labelled `legal-review` and stays open for comment for at least
   **14 days**.
3. A legal reviewer summarises the discussion and records the outcome. If
   consensus is not reached, the control is marked `contested` and the competing
   readings are summarised in its `interpretation.note`, with a link to the RFC.
4. The change ships in the next catalogue release, listed in the changelog.

Editorial fixes (typos, clearer wording with the same meaning, broken links)
and new checks for existing controls follow the normal pull-request process.

## Releases and versions

- **Catalogue versions** follow the law: `YYYY.MM` of the legal text they track,
  plus a sequence number, for example `2025.11-draft.1`. A new release follows
  each amendment, notification or Board guidance that changes obligations.
- **Software versions** follow semantic versioning. The report JSON schema
  (`dpdp-kit/report/v1`) changes only with a major version.

## Code of conduct

All participation is covered by the [Code of Conduct](CODE_OF_CONDUCT.md).
