# Isolated DHL non-browser integration checks (REX-70)

This test-only harness lives separately from the feature tree. `target.json`
records PR #213's explicit immutable target; the workflow reads the current PR
head and refuses a mismatch. It checks out and asserts both exact SHAs and saves
them with the run URL. Normal PR merge-commit CI remains separate evidence.

No production code, migration, API, provider configuration or secret is changed.
Only Rex merges. Staging, deployment, live DHL and production activation are not
authorized by this harness. REX-61 owns the feature; NightWing's REX-62 acceptance
and Groot's REX-64 verification remain independent gates.

## Local setup or run commands

Host-safe checks from the harness repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s qa/dhl -p test_containment.py -v
git diff --check
```

The full command below is only for an explicitly authorized isolated Docker/CI
runner, never a way to launch unmanaged Paperclip host services. Place the two
verified Git checkouts under `harness/` and `target/`; assert `git rev-parse HEAD`
against the recorded pins before building, exactly as the workflow does.

```sh
cp harness/qa/dhl/dockerignore .dockerignore
docker build -f harness/qa/dhl/Dockerfile -t dhl-qa:local .
docker run --name dhl-qa-local --network none --cap-drop ALL \
  --security-opt no-new-privileges --pids-limit 512 --shm-size 1g \
  --cpus 2 --memory 8g dhl-qa:local
# Even after a failed run:
docker cp dhl-qa-local:/evidence/. ./evidence/
docker rm -f dhl-qa-local
```

Dependencies are installed in the image before containment. Runtime has only
loopback, no host mounts, no published ports, no provider secrets, and no worker
or beat. A generated test signing key and disposable PostgreSQL configuration
exist only in that container. PostgreSQL uses a private, ephemeral cluster and
the existing ownership-fenced per-process database fixture. Runtime has no
privileges to reconfigure networking. The existing application lockfile controls JS packages.

## Local test steps

1. Prove OS IPv4/IPv6 external connections fail with no route, and only `lo`
   exists. A timeout/refused connection is insufficient. Failure aborts all feature tests.
2. Run focused DHL frontend tests (one Vitest worker), frontend lint and local-API build.
3. Run existing backend suites: admin orders, DHL operations, phase 4 booking,
   phase 4 static contracts, retaining their existing fixtures.
4. Run `python -m pytest -c /harness/pytest.ini /harness/test_http.py` in one process.
   It reuses the target's database lifecycle and package/quote/custody builders,
   with real FastAPI loopback HTTP and a separate database session per request.
5. Check ready-package projection/binding, real login, booking, binary labels,
   tracking, handoff, persisted unknown/timeout state, role/cross-order denial,
   pending-product privacy and financial snapshots. Existing backend tests retain
   concurrency/idempotency coverage. No DOM interaction or rendered UI is asserted.

Fixture controls are Python-only and never registered as routes. DHL uses the
actual client/parser with a deterministic HTTP transport. Email, payment,
storage and task-publication fakes raise before external effects. The four-operation
case expects notification failure before delivery; unexpected effects fail tests.

## Existing CI and remaining gap

`.github/workflows/ci.yml` already runs the backend suite, frontend build and product
upload tests on the PR merge checkout. Its frontend lint/type checks are advisory.
The retained dedicated job adds exact target/harness pins, fail-closed egress
containment, focused DHL frontend tests, strict lint/build results and actual
HTTP/auth/database checks. It does not add infrastructure beyond the existing job.
Browser QA belongs to Rex; no browser dependency, preview server or browser test
runs here. Existing UI test results are not rendered-browser evidence.

## Expected local result

Every individual check must pass, with per-test JUnit results.
Inspect `revisions.json`, `checks.json`, `containment.json`,
database teardown, process/cluster teardown and container teardown. Missing
evidence is a failed/incomplete gate, even if another CI job is green.

The job is bounded to 30 minutes and the runtime supervisor to 20 minutes,
with one test worker and no retries, schedules or dispatch. Only opening or
updating this harness PR triggers it. Rerun attempts are skipped and do not
constitute acceptance. A substantive fix/pin change needs a new revision.

## Staging test steps

Staging is untested. After separate authorization and merge/deployment, repeat
the feature checklist in `docs/qa/dhl-shipment-operations.md` from the target
revision with an approved synthetic sandbox cohort. Do not use these Python
fixture overrides or CI account values on staging.

## Expected staging result

The same role, package binding, custody, financial and retry guarantees hold.
Real provider/notification integration requires its separately approved checks.
This CI harness by itself does not unblock feature QA or authorize live use.

## Regression checks and evidence limitations

- Existing backend tests cover booking concurrency/idempotency, currency, custody,
  authorization, tracking and pickup contracts. HTTP checks compare financial
  snapshots, enforce label/role/cross-order denial and pending-product privacy.
- Browser confirmation, focus, cancellation, double-click and reload behavior are
  Rex-owned. There are no screenshots, traces or rendered-browser claims from this job.
- Only sanitized JUnit and status/containment/teardown metadata are published.
  Label bytes, tokens, private payloads, database dumps and process logs are excluded.
  Retention is seven days. There is no published preview URL.
- Local host-safe tests do not start services. Full runtime evidence must come from
  the authorized CI job. Staging remains untested; independent NightWing review
  and Groot's technical verification remain required. Only Rex merges.
- Initial run `36481744854` passed exact-SHA assertions, image build, IPv4/IPv6
  no-route probes and owned teardown, but failed PostgreSQL startup before feature
  tests. The socket-path correction was included at `85df77460bec7257593de8326937ceffee6e3c3d`.
  Browser-capable run `36482294123` was cancelled to enforce the narrowed scope.
  That historical revision preserves the removed work; it is not browser acceptance.
