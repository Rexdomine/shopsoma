# Isolated DHL acceptance runner (REX-70)

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
privileges to reconfigure networking. Chromium and its driver are pinned by
`playwright==1.55.0`; the existing application lockfile controls JS packages.

## Local test steps

1. Prove OS IPv4/IPv6 external connections fail with no route, and only `lo`
   exists. A timeout/refused connection is insufficient. Failure aborts all
   feature tests. Each browser fixture also proves external navigation fails.
2. Run focused DHL frontend tests (one Vitest worker), full frontend lint and
   local-API build. Results are separate gates, not `continue-on-error` passes.
3. Run actual existing backend suites: admin orders, DHL operations, phase 4
   booking, phase 4 static contracts. These retain their existing mocks within
   the externally disconnected container.
4. Run `python -m pytest -c /harness/pytest.ini /harness/test_browser.py` with a
   single pytest process. It reuses the target's conftest/database lifecycle and
   package/quote/custody builders, runs target FastAPI through loopback HTTP with
   a separate SQLAlchemy session per request, and logs in through the real UI.
   No Playwright route interception or application API mocking exists.
5. Browser checks cover zero/one/multiple ready packages, selection, modal
   focus/cancel, booking, binary label, tracking, handoff, concurrent distinct
   admins/double clicks, unknown/timeout/reload, roles, cross-order denial,
   pending-product privacy and unchanged financial snapshots.

Fixture controls are Python-only and never registered as routes. DHL uses the
actual client/parser with an injected deterministic HTTP transport. Email,
payment, storage and task publication fakes raise before external effects.
The four-operation test explicitly expects email delivery failure during status
notifications; it exercises the application's caught-failure behavior. It does
not approve or test real notification delivery. All other unexpected effects,
including swallowed exceptions, fail the scenario.

## Expected local result

Every individual check must pass, with actual screenshots and per-test JUnit
results. Inspect `revisions.json`, `checks.json`, both containment files,
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

- Backend suite covers existing order currency, booking concurrency, handoff
  custody, authorization and tracking contracts. Browser checks compare order
  and item financial fields, verify pending product detail denial and retain
  the unavailable DHL pickup behavior. General pickup regression coverage is
  limited to existing backend tests; it is not a rendered generic-pickup test.
- Screenshots are synthetic and mask form inputs. Raw Playwright traces/HAR,
  label files, login storage, database dumps and process logs are not uploaded.
  JUnit keeps outcomes/source locations while dropping captured logs and error
  payloads. Artifact retention is seven days. The CI artifact is the reproducible
  preview handoff; there is no remotely published preview URL.
- The suite intentionally fails on target or harness defects; no source reading
  is reported as rendered-browser evidence. Check the actual run before marking
  acceptance. CI runner/OS images and apt packages are not digest-pinned, so the
  source/browser pins do not imply bit-for-bit system reproducibility.
- Local services were not started by the authoring heartbeat. Full execution
  evidence must come from the authorized GitHub job and independent review.
