# Security Policy

## Supported versions

Security fixes are applied to the latest code on the default branch. Older snapshots and forks may not receive updates.

## Reporting a vulnerability

Please do not publish exploit details, credentials, account information, or sensitive logs in a public issue.

Use GitHub's private vulnerability reporting / security advisory feature for this repository when available. If that feature is unavailable, contact the repository owner privately through the GitHub profile and request a secure disclosure channel. Include the affected commit, impact, and minimal reproduction steps. Do not include real brokerage credentials or personal financial records.

We will acknowledge reports as soon as reasonably possible, validate the issue, and coordinate remediation and disclosure with the reporter. There is no guaranteed response or remediation SLA at this early stage.

## Current security boundaries

- FLY is an experimental, paper-only portfolio simulator.
- The current server is intended for localhost access only.
- Local owner password authentication is available, but there is no TLS or multi-user identity system.
- Alpaca integration is read-only market data; no brokerage order-submission endpoint exists.
- Public brokerage connectivity and live trading are not implemented.
- Portfolio marks are manually entered hypothetical prices.
- Local audit events are not tamper-evident.
- Do not expose the development server to the internet or use it to manage real-money portfolios.

A passing test suite is not a security certification. Before production use, the project requires independent security review, authentication and authorization, secure deployment configuration, monitoring, and tested disaster recovery.
