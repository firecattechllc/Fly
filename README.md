# FLY — Portfolio Intelligence

**FLY** is an original, self-hosted, MIT-licensed portfolio analysis and paper-trading cockpit. Its design takes inspiration from institutional risk-monitoring workflows; it is **not affiliated with BlackRock or Aladdin** and uses no BlackRock IP or proprietary risk models.

## What works

- Responsive dark institutional-style dashboard with portfolio breakdown and navigation.
- Durable local SQLite simulated cash, holdings, orders and last 30 activity events.
- Paper-only order tickets, long-only equities, 10% equity buy notional limit, no brokerage orders.
- Transparent, deterministic risk analytics: cash weight, gross exposure, position concentration, -5/-10/-20% uniform holding-price shock scenarios.
- Read-only Alpaca IEX/delayed-SIP stock quote adapter (requires separately injected credentials; currently unconfigured).
- No automatically updated marks: all portfolio position values use the last price manually entered in the paper ticket.
- Localhost-only service, Host restrictions and anti-CSRF request token.
- Verified SQLite online-backup script and a GitHub Actions unit-test workflow.

## MacBook Air development

The native macOS agent is `tech.firecat.fly`, with host `127.0.0.1:8877`. Visit <http://127.0.0.1:8877> on the host.

```sh
python3 -m unittest discover -s tests -v
python3 backup.py
launchctl kickstart -k "gui/$(id -u)/tech.firecat.fly"
curl -fsS http://127.0.0.1:8877/healthz
```

## Mac mini deployment — planned, not yet cut over

The Docker Compose file publishes only to mini's loopback and uses a managed `fly-data` Docker volume with an unprivileged container account. From a clean checkout on the mini:

```sh
docker compose up -d --build
docker compose ps
curl -fsS http://127.0.0.1:8877/healthz
```

Do not activate a second account as authoritative until the approved data migration, restore verification, and host cutover have been completed. `data/` is excluded from git; transfer it using a secure backup and verified restore, never via a public GitHub repository.

## Market data credentials

`GET /api/quotes?symbols=AAPL,MSFT&feed=iex` uses Alpaca's HTTPS market-data API. On macOS, the adapter resolves the existing login-Keychain service `com.firecattechnology.Sigil.dev.credentials` with accounts `alpaca_api_key` and `alpaca_secret_key` immediately before the request. It never stores or logs credential values. Explicit process environment variables are supported for isolated deployments and tests only. Missing or inaccessible Keychain items fail closed with HTTP 503. Alpaca remains data-only; quote access does not authorize brokerage orders.

## Reality checks

**FLY is an early paper-only prototype, not production-certified.** There is no multi-user identity system, provider-account reconciliation, historical returns engine, validated VaR, live portfolio valuations, secure remote UI exposure, full disaster recovery drill, or institutional certification. Local SQLite paper events are *not* tamper-evident. Hypothetical shock analysis does not predict real future market behavior.

Keep local HTTP bound to `127.0.0.1`. Before any external exposure: implement authentication, TLS, session management, monitoring, privilege separation, security audit, and recovery tests. Before any real-money use: require explicit user approval, additional broker-specific controls, formal review, and separate deployment procedures. Public.com is not integrated.

## Tests

```sh
python3 -m unittest discover -s tests -v
node --check static/app.js
python3 -m py_compile app.py risk.py market_data.py backup.py
```

© 2026 FLY contributors. MIT License.


## Public source / preproduction development

The owner has elected to make the GitHub repository **public** before production certification. Source code is available under the MIT license, but the running application is still an experimental local development build. Do not publish or commit any credentials, account records, owner-authentication files, session tokens, or SQLite backups.

## Alpaca credential handling on macOS

The Air's intended Keychain item is service `com.firecattechnology.Sigil.dev.credentials`, with accounts `alpaca_api_key` and `alpaca_secret_key`, in the user's login Keychain. The adapter retrieves values just-in-time with macOS `security` and passes them only in the HTTPS request headers. It never prints, logs, stores, or returns the values. If either item is missing or Keychain access is denied, the quote request fails closed. No credentials were found on the current Air during the last check; quote endpoint therefore returns HTTP 503 until those two items are available.

Alpaca remains market-data only. Public is the intended actual brokerage path, but its prior 2FA recovery issue remains unresolved. Do not attempt Public authentication, enable Public integration, or submit orders until account access and the user's explicit approval are confirmed. Paper simulator events and balances are separate from actual Public account state.

## Release policy

Do not expose the service beyond localhost or enable live order submission during development. Public source availability does **not** mean FLY is production-certified or approved for real-money trading.

## FLY owner login (local development)

The localhost dashboard now requires an owner password. On the first visit to `http://127.0.0.1:8877/auth`, the owner creates a unique password with at least 14 characters. The password itself is never written to disk; a salted PBKDF2-SHA256 hash is stored in `data/owner-auth.json` with restrictive permissions. The file is excluded from Git.

A successful login creates an 8-hour, memory-only, HttpOnly, SameSite=Strict session cookie. The browser UI uses a per-session CSRF token for simulated orders and logout. Five incorrect login attempts trigger a 15-minute per-IP lockout. Signing out or restarting the service invalidates the session. Static dashboard code and portfolio APIs require a valid session; the health endpoint and login assets are available without a session. The bootstrap flow is for a trusted owner at the Mac, not public internet hosting.

**Important:** There is no self-service password recovery yet. Keep your owner password in a password manager. If it is lost, restoring access requires local operating-system access to reinitialize the development owner credentials; never delete owner-auth.json without first verifying you are on the correct host and have an approved recovery plan.

For the mini Docker deployment, `FLY_AUTH_PATH=/data/owner-auth.json` keeps the owner hash with the persistent data mount. The database and authentication file must be backed up securely before migration; moving code via GitHub does not move identity or trading simulation data. Do not put an actual owner password, cookie, session token, or the authentication file in GitHub, screenshots, or chat.

This is a meaningful local security improvement but is not a production-grade multi-user identity system. TLS, secure public access, stronger session governance, independent security review, and disaster recovery remain required before production sign-off.

## Owner and portfolio recovery pair

The daily `backup.py` job now creates two paired files in `~/FLY-Backups`: `fly-<timestamp>.sqlite3` (the paper portfolio) and `fly-<timestamp>.owner-auth.json` (the salted owner password verifier). Both use mode `0600` under a private mode `0700` backup directory. The owner verifier is sensitive security material even though it does not contain the plaintext password; never upload it to GitHub or share it publicly. Local backups are not encrypted or off-device disaster recovery.

Run `python3 recovery_check.py` to inspect the latest paired backup without altering the live application. This checks SQLite integrity, presence of portfolio tables, owner-record shape, and permissions. It does not test a full system restoration or prove that the user's actual password works after migration. For disaster recovery, an encrypted off-device copy and an isolated end-to-end restore/login drill are still required.

## Paper equity observations

FLY records an initial observation of the currently held *hypothetical* portfolio and a new valuation after each paper order, in the same SQLite transaction as the order. The authenticated `GET /api/performance` endpoint (documented without backticks escaping below) exposes up to 120 recent observations for the dashboard line chart. These are sampled **paper account equity marks**, not daily NAV, true market history, investment returns, historical backtests, or broker valuations. There are no estimated returns for periods before the first observation. The initial observation for an existing database uses its present cash and manual marks rather than pretending earlier trades have been priced historically.

API endpoint: `/api/performance`. No credentials, portfolio database, or login verifier belong in GitHub.

## Mini staging and least-privilege container

The mini deployment is **not yet cut over**. A staging smoke test of FLY passed on the mini without connecting real brokerage credentials or moving the Air's owner record or paper portfolio.

The release image runs as unprivileged UID 10001 with a read-only root filesystem, no Linux capabilities, `no-new-privileges`, and a persistent managed Docker volume. The container's local HTTP service binds only to host loopback. On a future approved mini migration, **do not run Compose for the authoritative service until** the current Air recovery pair has been securely copied and restored into the persistent `fly-data` volume and owner login verified; Compose on an empty volume would create a distinct blank paper account.

`FLY_HOST=0.0.0.0` inside Docker is necessary for publishing the container through the host's `127.0.0.1:8877` port mapping. Do not use `0.0.0.0` on the host's published port. This release remains a development system until authenticated access, restore testing, update policy, rate limiting and monitoring receive an independent review.

## Alpaca market-data connection

The HTTP adapter can request IEX/delayed-SIP stock quotes using just-in-time macOS Keychain credentials, but no accessible Air Keychain entries have been verified. Do not place credentials into GitHub issues, public source files, environment configuration in GitHub, or chat. Provider connectivity must be confirmed explicitly before the UI labels it operational. FLY never uses market quotes to execute real orders.

## Historical stock bars and research panel

The owner-authenticated Market Monitor now supports `GET /api/historical?symbol=SPY&days=90&feed=iex` for daily OHLCV bars and `GET /api/research?symbol=SPY&days=90&feed=iex` for derived, reproducible market statistics. Both are **read-only** and require the server's own Alpaca market-data credentials. The Mac's Keychain credentials are still missing or inaccessible; the connected ChatGPT Alpaca app credentials are not transferred into the local FLY service.

Inputs are restricted to one valid US equity symbol, IEX/delayed SIP, a 5–365 calendar-day lookback, and up to 400 daily bars per response. The server uses Alpaca's HTTPS market-data endpoint with a 20-minute freshness cutoff to avoid requesting data too recent for delayed feeds. The broker account, portfolio valuation, and paper order execution remain completely separate. A missing provider credential fails closed; no fabricated sample prices are displayed as live data.

The research panel computes **unadjusted historical close-to-close change**, 20/50-observation simple moving averages, and sample annualized close-to-close volatility. These are descriptive, may be biased by a limited single-exchange feed, and ignore dividends and corporate-action adjustments. No strategy signals, AI model, price forecasts, personalized recommendations, or real-money trading are active. A future AI narrative service requires its own model security, data quality checks, audit policy, and user approval before activation.

## Read-only market data request budget

Authenticated historical OHLCV and research requests share a bounded, in-memory cache: at most **64 symbol/feed/lookback records** with five-minute time-to-live. The latest-quote monitor uses a separate key namespace and a 15-second TTL. Repeated UI requests return copies; callers cannot mutate cached objects, unsuccessful provider requests are not cached, and the cache disappears when the process restarts. This reduces duplicate provider traffic but **does not** guarantee data freshness at trade time and must not be used to automate orders. The historical/research endpoints remain distinct from paper portfolio marks and never trigger brokerage execution. A production upstream quota policy and instrumentation are still outstanding.
