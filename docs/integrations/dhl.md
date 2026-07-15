# DHL Express MyDHL API integration

## Status

Phase 1 provides a disabled-by-default, secret-safe HTTP foundation. It does **not** call DHL from checkout, calculate rates, create shipments, update orders, or alter the database.

Current public reference: [MyDHL API (DHL Express) v3.3.1](https://developer.dhl.com/api-reference/dhl-express-mydhl-api)

## Environments

- Sandbox: `https://express.api.dhl.com/mydhlapi/test`
- Production: `https://express.api.dhl.com/mydhlapi`

The application selects one of these fixed URLs from `DHL_ENVIRONMENT`. It does not accept an arbitrary base URL.

## Authentication and secrets

MyDHL API authorization credentials are distinct from the DHL developer-portal login. Do not put either credential set in source control, tickets, screenshots, logs, test fixtures, or chat messages.

Configure deployment secrets through the environment/secret manager:

```dotenv
DHL_ENABLED=false
DHL_ENVIRONMENT=sandbox
DHL_API_USERNAME=
DHL_API_PASSWORD=
DHL_EXPORT_ACCOUNT_NUMBER=
DHL_IMPORT_ACCOUNT_NUMBER=
DHL_REQUEST_TIMEOUT_SECONDS=30
```

Credential and account fields are `SecretStr` values in application settings. When `DHL_ENABLED=true`, the application refuses to start unless API username, API password, and export account number are present. The validation error lists only missing field names.

`DHL_IMPORT_ACCOUNT_NUMBER` remains optional until an approved import-account flow requires it.

## Safe activation and rollback

- Default and rollback state: `DHL_ENABLED=false`.
- Phase 1 contains no shipping route or checkout hook, so enabling the flag alone still does not initiate a DHL request.
- Never switch `DHL_ENVIRONMENT=production` or add production credentials before DHL UAT/certification and explicit launch approval.
- Never log request/response bodies for DHL calls: they can contain addresses, contact details, declared values, customs data, and credentials/account references.
- The low-level client does not log paths, query parameters, request bodies, or response bodies. Query strings are rejected in `path`; callers must use the separate `params` argument.
- Authorization, Accept, and Content-Type are client-managed headers and cannot be overridden by callers.

## Error contract

`DHLClient.request_json()` maps upstream failures to `DHLAPIError`:

- `400` and other ordinary 4xx validation failures: not retryable
- `401`: authentication failure, not retryable
- `403`: authorization failure, not retryable
- `429`: rate limited, retryable by an operation-specific policy
- `5xx`: upstream unavailable, retryable by an operation-specific policy
- timeout/network failure: retryable by an operation-specific policy
- malformed successful response: not retryable by default

Phase 1 intentionally performs no automatic retries. Quote operations may later use bounded retries; shipment creation and other side effects require idempotency rules before any retry is safe.

## Phased rollout and resource gates

### Phase 1 — Provider foundation

Included:

- validated, disabled-by-default settings
- fixed official environment URLs
- Basic-auth HTTP client boundary
- secret-safe logs and exceptions
- deterministic unit tests with no live DHL call

Excluded:

- database migrations
- product customs/package fields
- checkout and frontend changes
- live quote, shipment, pickup, tracking, cancellation, webhook, or polling calls

### Phase 2 — Address capability and live quote

Required before implementation:

1. DHL Integration Manual and API JSON/Postman collection from the authorized portal/client.
2. Confirmed sandbox export account reference.
3. Canonical ShopSoma shipper details: legal/contact name, phone, email, street lines, city, postal code, country code.
4. International destination launch policy: all supported destinations or an explicit allowlist.
5. Product/package measurement policy: actual per-SKU weight and dimensions or approved category defaults.
6. Quote currency, FX source, rounding and checkout-display policy.
7. Duties/taxes policy: receiver-paid versus shipper-paid/landed-cost display.

Planned deliverables:

- address capability validation
- typed DHL rating request/response adapter
- provider-neutral server-side quote record with price, currency, service/product code and expiry
- server-side quote revalidation during order review/create
- no trust in client-submitted shipping prices

### Phase 3 — Shipment creation and label

Required before implementation:

- shipment trigger in the ShopSoma order lifecycle
- export/import account selection rules
- customs invoice source, HS code and origin-country policy
- insurance, declared value, packaging, pickup/drop-off decisions
- approved sandbox shipment cases
- idempotency key and duplicate-shipment prevention design

### Phase 4 — Tracking and operations

Required before implementation:

- polling/webhook capability confirmed from the supplied DHL specification
- status mapping into ShopSoma fulfillment states
- admin workflows for label download, pickup, cancellation and exceptions
- customer notification wording and ownership

### Phase 5 — Production activation

Required before implementation:

- completed sandbox/UAT evidence and DHL certification where required
- production authorization credentials in the deployment secret manager
- approved launch destinations and product scope
- monitoring, alerting, support ownership and rollback drill
- explicit client and Rex production approval

## Relevant code

- `app/core/config.py`
- `app/services/dhl/client.py`
- `tests/test_dhl_config.py`
- `tests/test_dhl_client.py`
- `.env.example`
