# Security policy

## Reporting a vulnerability

Do not disclose vulnerabilities, credentials, personal information, or sensitive source material in public issues, pull requests, or logs.

Use GitHub private vulnerability reporting through this repository's **Security → Advisories → Report a vulnerability** entry when available. Include the affected revision, impact, and minimal reproduction steps with synthetic or redacted data; never include live credentials.

The repository may be public. Private vulnerability reporting depends on GitHub availability and administrator settings; this policy does not claim it is enabled. If the reporting entry is unavailable, contact a repository administrator through an existing private GitHub collaboration channel and request a confidential reporting route. Do not open a public issue as a fallback. Administrators should enable GitHub private vulnerability reporting before public release.

## Trust boundaries

Secrets belong only in GitHub Actions secrets or local environment variables, never committed files. Fork pull requests receive secret-free validation and tests. The separate actual-value credential scan is restricted to main pushes, manual dispatch, and same-repository pull requests, and fails when its required secret is absent. Repository visibility is not a substitute for review of workflows, source rights, or sensitive data.

Only the current main revision is maintained; reports concerning older revisions should identify whether the issue also affects main. No response-time guarantee is made.
