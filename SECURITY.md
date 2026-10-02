# Security policy

## Reporting a vulnerability

Please do not open a public issue for security problems. Use GitHub's
**private vulnerability reporting** (Security → Report a vulnerability) once the
repository is public. We aim to acknowledge reports within 5 working days.

## Scope notes

- The kit runs locally and loads target websites in a headless browser. Treat
  untrusted target sites as you would any untrusted web content.
- `--plugins-dir` and installed plugins execute arbitrary Python. Only load
  plugins you trust.
- Reports can contain screenshots and network logs of the target site. Handle
  them according to your own data-classification rules before sharing.
