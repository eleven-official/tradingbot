# Tradovate funded-account connections

Open **AI trading → Funded / Tradovate**. The three workspace buttons show one
account workflow at a time. Switching views does not start or stop a runner.

## Connection methods

**TradersPost:** the guided setup opens the external service. Its documented
Lucid integration uses Tradovate authorization. Accounts and automation configured
there belong to TradersPost; opening the link never reports a Loki connection.

**Direct account viewing:** sign in to Loki and expand the API-token connection.
Choose the server assigned by the firm, then supply an access token obtained
through the official Tradovate API. Funded/evaluation accounts can use the demo
server; this is not the same as Loki's paper simulator. A market-data token,
account password, or API secret is not an access token.

Loki verifies `/account/list`, then reads `/position/list` and `/cashBalance/list`.
The account picker filters the returned records. Missing read permissions are
shown as unavailable, never as a fabricated zero balance or flat position.
Contract and currency identifiers are displayed as supplied by the API.
This connection does not implement futures orders or automatically trade a funded
account. The existing Alpaca controls remain separate.

## Deployment

Set `LOKI_BROKER_ENCRYPTION_KEY` to a Fernet key generated with:

```python
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
```

Store it only in server environment configuration. The same production key must
be available across serverless invocations. Rotation disconnects existing links.
The access token is carried in an encrypted HttpOnly, SameSite=Strict cookie,
scoped to `/api/account/funded`, and expires after at most one hour. HTTPS uses
Secure cookies. Plaintext credentials never enter browser storage, account
workspace backups, JSON responses or source control. Disconnect removes the
connection cookie; it does not revoke the broker-issued token at Tradovate.

Direct OAuth is not configured: Tradovate must issue application credentials and
register the callback before a genuine one-click login can be offered. The
external TradersPost option provides its own supported authorization flow.

References checked during implementation:
- https://api.tradovate.com/
- https://github.com/tradovate/example-api-oauth
- https://traderspost.io/connections/lucid-trading

Offline tests cover owner isolation, expiry, encryption, credential redaction,
fixed-host requests, partial reads, account filtering and UI interaction. A real
funded account still requires the account holder's token or external authorization
for an end-to-end live verification.
