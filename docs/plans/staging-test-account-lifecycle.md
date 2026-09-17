# Staging test-account lifecycle

## Classification scope

The classifier targets every existing `customer` and `vendor` row in the **staging** database. It never infers test status from email addresses and never includes `admin` or service accounts.

`POST /api/v1/admin/test-accounts/classify` is dry-run by default:

```json
{"apply": false}
```

After the migration is deployed to staging, an authorized staging admin may apply the classification with:

```json
{"apply": true}
```

The operation is idempotent. Each newly tagged account receives a timestamp, the acting admin ID, a fixed reason, and an audit event. Re-running it reports zero newly tagged rows.

## Purge gate

This PR does **not** execute or enable account deletion. A complete purge must be a separate, explicitly authorized operation that:

1. accepts only the staging environment;
2. previews exact customer/vendor IDs and dependent-row counts;
3. refuses if any eligible account is unclassified;
4. excludes admins and service identities by role at the database boundary;
5. handles payment, order, fulfilment, inventory, vendor, address, cart, wishlist, media, and audit dependencies according to their ownership/retention policy;
6. records a purge run, per-account result, and failure/recovery state; and
7. requires a unique confirmation token after the preview has been read back.

The existing single-user hard-delete route is not a valid bulk-purge primitive because several historical and operational foreign keys intentionally use `RESTRICT`. No staging accounts are deleted by this change.
