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

## Verified client-supplied contract

The client-supplied integration manual, Postman collection, and checkpoint-code workbook were reviewed outside Git. Raw client source files must not be committed.

DHL's recommended operation order is:

1. address validation
2. rates
3. shipment creation
4. pickup
5. tracking

Verified request rules:

- use `GET /address-validate`, `POST /rates`, `POST /shipments`, `POST /pickups`, `DELETE /pickups/{dispatchConfirmationNumber}`, and `GET /shipments/{trackingNumber}/tracking`
- use metric weights and dimensions
- use product code `N` for domestic shipments, `D` for international documents, and `P` for international packages
- domestic shipments are not customs-declarable; international packages are customs-declarable
- shipment requests set `pickup.isRequested=false` because pickup is a separate operation
- international packages require detailed customs line items, manufacturer country, declared value/currency, and commodity/HS codes supplied by the merchant
- rate examples use the shipper account role and `nextBusinessDay=true`
- shipment examples use PDF output and DAP, subject to client confirmation before shipment implementation

Source constraints:

- the Postman collection contains request examples but no response examples and no executable collection-level authentication
- 9 of 18 raw request bodies contain comments and are not valid strict JSON without normalization; the collection is illustrative and must never be sent verbatim
- fields present in examples are not automatically mandatory fields; requiredness must be verified against the official schema and sandbox behavior
- example customer, pickup, shipment, and tracking values are sample data and must not be reused
- the address example's hardcoded city is sample data; ShopSoma must submit the actual destination city
- use the plural `/shipments` route; a singular route mention in the manual conflicts with its examples, the collection, and the official API
- one domestic pickup example uses `D` despite the manual and other domestic examples requiring `N`; treat it as a source defect pending DHL confirmation
- the client workbook contains 38 unique checkpoint codes as a clean Phase 4 seed, but has no version/effective date or lifecycle semantics and is not yet a production authority
- the supplied sources verify tracking polling through `GET`; they do not establish webhook support or a shipment-cancellation endpoint

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
- live quote, shipment, pickup, pickup deletion, tracking, webhook, or polling calls

### Phase 2 — Address capability and live quote

Required before implementation:

The integration manual and API collection have been received and reviewed. The remaining gate is:

1. Confirmed sandbox API credential set and export account reference.
2. Canonical ShopSoma shipper details: legal/contact name, phone, email, street lines, city, postal code, and country code.
3. Initial shipment scope: outbound physical merchandise only, or additional document/import flows.
4. International destination launch policy: all supported destinations or an explicit allowlist.
5. Product/package measurement policy: actual per-SKU weight and dimensions or approved category defaults.
6. Planned-shipping-date policy, operating timezone, and business-day cutoff.
7. Quote currency, FX source, rounding, margin/handling, expiry, and checkout-display policy.
8. Duties/taxes and Incoterm policy: receiver-paid/DAP versus shipper-paid/landed-cost display.
9. Address-validation failure policy: block checkout, request correction, or an explicitly reviewed exception path.
10. Fulfillment-origin model: centralized ShopSoma dispatch or vendor-origin shipping.
11. Multi-vendor policy: consolidation versus split shipments and which origin/account rates each package.
12. Account-routing policy by origin, destination, payer, and shipment direction.
13. Packaging model: one or multiple packages, dimensional aggregation, volumetric-weight handling, and fallback measurements.
14. Destination-specific address mapping for postal code, state/county, and address lines.
15. Sandbox acceptance matrix covering domestic/international, invalid address, unsupported destination, timeout, rate limit, and no-service cases.

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
- explicit void/recreate policy; the supplied material verifies pickup deletion but not shipment cancellation

### Phase 4 — Tracking and operations

Required before implementation:

- tracking polling cadence, backoff, rate-limit budget, retention, and terminal-state stopping rules
- webhook support confirmed separately from the official DHL contract if event-driven updates are desired; it is not evidenced by the supplied files
- status mapping into ShopSoma fulfillment states
- admin workflows for label download, pickup, pickup deletion, tracking exceptions, and any separately verified shipment-void capability
- customer notification wording and ownership
- pickup operational rules including cutoff, close time, location/type, instructions, dispatch-confirmation retention, and authorized deletion reasons/requestor identity

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
