# Security policy

## Reporting a vulnerability

Do not disclose vulnerabilities, credentials, personal information, or sensitive source material in public issues, pull requests, or logs.

Use GitHub private vulnerability reporting through this repository's **Security → Advisories → Report a vulnerability** entry when available. Include the affected revision, impact, and minimal reproduction steps with synthetic or redacted data; never include live credentials.

As part of the publication procedure, the maintainer enables GitHub private vulnerability reporting when the repository becomes public. If the reporting entry is still unavailable, open a public issue titled **Security contact request** with NO vulnerability details, credentials, personal information, or sensitive source material. A maintainer will then open a private channel, for example a draft security advisory with the reporter added as a collaborator. Share vulnerability details only through that private channel.

## Trust boundaries

Secrets belong only in GitHub Actions secrets or local environment variables, never committed files. Fork pull requests, pull requests targeting a branch other than main, and pull requests authored or run by Dependabot receive secret-free validation and tests, including a blocking tracked-file credential-shape scan before tests. The pattern scan detects OC assignments/URLs, provider token shapes, private-key PEM headers, and long high-entropy generic secret assignments without receiving secrets. Findings show only file, line, rule ID and a masked marker. Obvious placeholders and environment references pass; reviewed exceptions are limited to exact path/rule/line hashes documented in tools/pattern_scan.py. The separate actual-value credential scan is restricted to main pushes, manual dispatch, and same-repository pull requests targeting main whose author and actor are both not Dependabot, and fails when its required secret is absent. Repository visibility is not a substitute for review of workflows, source rights, or sensitive data.

The pattern scanner is a best-effort, secret-free heuristic for untrusted PRs. It checks single-line assignment forms and provider-specific token shapes. Credential names use case-insensitive word segments (snake_case, kebab-case, dotted and camel/Pascal forms). After assignment-like operators, it inspects every candidate after optional type annotations: quoted literals with Python prefixes, backtick static parts, shell expansion operands and bare tokens. Only whole placeholders, empty values and pure environment references with no literal fallback are exempt; literal shell fallbacks are inspected. OC candidates use the non-placeholder rule; generic credentials require length >= 20 and Shannon entropy >= 3.5. Diagnostics never print values; exceptions remain exact path/rule/whole-line hashes.

It does not detect multi-line constructions, computed or obfuscated values, or encodings beyond UTF-8/UTF-16. The authoritative control is the value-based `credential-scan` (LAW_OC) that runs on trusted events and on every push to main, plus maintainer review.

Only the current main revision is maintained; reports concerning older revisions should identify whether the issue also affects main. No response-time guarantee is made.
