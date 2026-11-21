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

The Docker Compose file publishes only to mini's loopback. From a clean checkout on the mini:

```sh
docker compose up -d --build
docker compose ps
curl -fsS http://127.0.0.1:8877/healthz
```

Do not activate a second account as authoritative until the approved data migration, restore verification, and host cutover have been completed. `data/` is excluded from git; transfer it using a secure backup and verified restore, never via a public GitHub repository.

## Market data credentials

`GET /api/quotes?symbols=AAPL,MSFT&feed=iex` uses Alpaca's HTTPS market-data API. On macOS, the adapter resolves the existing login-Keychain service `com.firecattechnology.Sigil.dev.credentials` with accounts `alpaca_api_key` and `alpaca_secret_key` immediately before the request. It never stores or logs credential values. Explicit process environment variables are supported for isolated deployments and tests only. Missing or inaccessible Keychain items fail closed with HTTP 503. Alpaca remains data-only; quote access does not authorize brokerage orders.

## Reality checks

**FLY is an early paper-only prototype, not production-certified.** There is no user sign-in, provider-account reconciliation, historical returns engine, validated VaR, live portfolio valuations, secure remote UI exposure, full disaster recovery drill, or institutional certification. Local SQLite paper events are *not* tamper-evident. Hypothetical shock analysis does not predict real future market behavior.

Keep local HTTP bound to `127.0.0.1`. Before any external exposure: implement authentication, TLS, session management, monitoring, privilege separation, security audit, and recovery tests. Before any real-money use: require explicit user approval, additional broker-specific controls, formal review, and separate deployment procedures. Public.com is not integrated.

## Tests

```sh
python3 -m unittest discover -s tests -v
node --check static/app.js
python3 -m py_compile app.py risk.py market_data.py backup.py
```

© 2026 FLY contributors. MIT License.


## Private production-preparation phase

The GitHub repository is intentionally **private**. Public open-source release is a final milestone only after production-readiness review, security review, provider validation, recovery testing, and owner approval. Do not change repository visibility before that approval.

## Alpaca credential handling on macOS

The Air's intended Keychain item is service `com.firecattechnology.Sigil.dev.credentials`, with accounts `alpaca_api_key` and `alpaca_secret_key`, in the user's login Keychain. The adapter retrieves values just-in-time with macOS `security` and passes them only in the HTTPS request headers. It never prints, logs, stores, or returns the values. If either item is missing or Keychain access is denied, the quote request fails closed. No credentials were found on the current Air during the last check; quote endpoint therefore returns HTTP 503 until those two items are available.

Alpaca remains market-data only. Public is the intended actual brokerage path, but its prior 2FA recovery issue remains unresolved. Do not attempt Public authentication, enable Public integration, or submit orders until account access and the user's explicit approval are confirmed. Paper simulator events and balances are separate from actual Public account state.

## Release policy

Do not expose the service beyond localhost, do not enable live order submission, and do not make the GitHub repository public during this preparation phase. Public release is the final step after production sign-off.
