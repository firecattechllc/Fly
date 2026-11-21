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

`GET /api/quotes?symbols=AAPL,MSFT&feed=iex` uses Alpaca's HTTPS market data API with `APCA_API_KEY_ID` and `APCA_API_SECRET_KEY` provided securely to the **server process**. No credentials are stored in the repository or frontend. Do not place keys into a GitHub commit, LaunchAgent plist, browser, or chat. If no keys are configured, the endpoint fails closed with a 503 status. Alpaca quote access does not imply Alpaca brokerage authorization or any right to trade.

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
