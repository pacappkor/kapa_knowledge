# Security policy

## Reporting a vulnerability

Do not disclose vulnerabilities, credentials, personal information, or sensitive source material in public issues, pull requests, or logs.

Use GitHub private vulnerability reporting through this repository's **Security → Advisories → Report a vulnerability** entry when available. Include the affected revision, impact, and minimal reproduction steps with synthetic or redacted data; never include live credentials.

As part of the publication procedure, the maintainer enables GitHub private vulnerability reporting when the repository becomes public. If the reporting entry is still unavailable, open a public issue titled **Security contact request** with NO vulnerability details, credentials, personal information, or sensitive source material. A maintainer will then open a private channel, for example a draft security advisory with the reporter added as a collaborator. Share vulnerability details only through that private channel.

## Trust boundaries

Secrets belong only in GitHub Actions secrets or local environment variables, never committed files. Fork pull requests, pull requests targeting a branch other than main, and pull requests authored or run by Dependabot receive only secret-free validation and tests. The separate actual-value credential scan is restricted to main pushes, manual dispatch, and same-repository pull requests targeting main whose author and actor are both not Dependabot, and fails when its required secret is absent. Repository visibility is not a substitute for review of workflows, source rights, or sensitive data.

Only the current main revision is maintained; reports concerning older revisions should identify whether the issue also affects main. No response-time guarantee is made.
