# Verification and release notes

Results below were recorded on 11 October 2026 on Windows and Linux with Python 3.12, Node.js 22–24, PostgreSQL 16, Redis 7, a Celery worker and Chromium. They are local results, not a hosted deployment or a trial on bank data.

## What changed in v2

| Area | Change and how it is tested |
| --- | --- |
| FX rounding | Equal non-USD amounts are no longer labelled `FX_ROUNDING`; a matcher test covers equal values |
| Uploads | Both files are validated line by line before replacement, and a failed upload never reports success; API tests run the real importer and matcher |
| Duplicates | Uploaded rows keep their own row keys, so every repeated transaction ID reaches the duplicate detector; tested on both feeds |
| Review decisions | Byte-identical uploads are a no-op and stable break keys keep resolutions across reruns; a changed file replaces the result set explicitly |
| Money and time | Portable UUID, exact decimal and UTC timestamp types; a large-value round-trip is tested on both databases |
| Statistics | Counts come from the feeds the matcher actually compared |
| Errors | Typed query validation, line-specific CSV errors, visible connection and job failures, bounded polling |
| Concurrency | Dataset locks, a one-active-job index and transactional publication; admission, rollback and task-redelivery tests |
| Dashboard | Sorting happens across all pages, the UI is split into focused components, and the evidence panel is keyboard accessible |
| Matching speed | Fuzzy fallback uses an amount-sorted window with binary search; a randomized test checks it against a full scan, plus a 10,000-row scale test |
| Display | Amounts show cents, with sub-cent digits only when present; fonts are bundled, so the demo makes no third-party requests |
| Access and audit | Optional `API_KEYS` sign-in names the reviewer; resolve and reopen take notes; append-only `break_events` survive dataset replacement |
| Hosted databases | `?sslmode=require` URLs work with both database drivers; the suite runs over SSL |
| Dependencies | FastAPI and Starlette updated; dependency scans report no known vulnerabilities |
| Public demo | A static sample mode with browser-local review state, tested with zero API requests |
| Tooling | Ad-hoc scripts replaced by API, migration and browser tests that run in CI; unused assets, duplicate loaders and an unused hosting blueprint removed; a chart library replaced by a small CSS bar |

## Checks

| Check | Local result |
| --- | --- |
| Matcher, auth/audit, real API and migration suite on SQLite | 80 passed |
| Same suite with PostgreSQL 16 API storage | 80 passed |
| Migrated schema compared with the models (Alembic autogenerate) | No drift on SQLite or PostgreSQL |
| Browser-state and formatting unit tests | 6 passed |
| Built demo in Chromium, desktop 1440 px and mobile 390 px | Passed: pagination, filters, sorting, evidence, resolve, replay, refresh, reset, export, Escape and no horizontal page overflow |
| Connected browser → API → Redis/Celery → PostgreSQL | Passed: upload sample pair, 3 expected breaks, review, resolve, unchanged rerun, reload and filtered CSV. Re-run with `API_KEYS` set: wrong key rejected, sign-in, resolve with note, history shows the reviewer |
| Upgrade of a live PostgreSQL database from the first to the second migration | Applied on API startup; existing breaks and resolutions kept |
| Queued bundled sample, then unchanged rerun | 5,115 ledger rows, 130 detected; 130 inserted first run and 0 second run |
| Demo regeneration consistency | Committed JSON matches the seeded generator and current matcher |
| Ruff, frontend lint/format and optimized build | Passed |
| Dependency advisory scans | `pip-audit -r backend/requirements.txt` and full `npm audit` (including build tools): no known vulnerabilities at check time |

The API suite uses isolated databases and the actual application. AI calls are stubbed; no provider response or quality is claimed. Legacy upgrades preserve data and resolutions on both databases; a failed upgrade must roll back the original tables. PostgreSQL migration tests create and remove their own isolated schemas. The test client currently emits an upstream HTTPX deprecation warning. Browser checks use Chromium; other browsers and hosted networking have not been verified.

## Reproduce PostgreSQL checks

Start the isolated test database from the repository root:

```sh
docker compose -f backend/tests/compose.yml up -d --wait
```

PowerShell, with the Python environment active:

```powershell
$env:TEST_DATABASE_URL = 'postgresql://recon_test:recon_test@127.0.0.1:15432/ledger_recon_test'
python -m pytest backend/tests -q
Remove-Item Env:TEST_DATABASE_URL
```

On Linux/macOS, prefix the test command with `TEST_DATABASE_URL=postgresql://recon_test:recon_test@127.0.0.1:15432/ledger_recon_test`. The fixture wipes the test database between API cases. Never point it at a database you need to keep. `TEST_POSTGRES_PORT` can override the test port.

```sh
docker compose -f backend/tests/compose.yml down
```

## Reproduce the connected browser check

Start a disposable local Compose stack using the deployment guide, then from `frontend`:

```powershell
$env:LIVE_URL = 'http://localhost:5173'
npm run test:connected
```

If the server sets `API_KEYS`, also set `API_KEY` to one key and `API_REVIEWER` to its reviewer name. The test then checks a rejected key, sign-in and the recorded reviewer.

This test replaces the uploaded pair with fictional sample rows. It accepts only localhost/127.0.0.1 URLs. The default demo browser test starts and stops its own preview server; run `npm run build` first. Set `SCREENSHOT_DIR` to a directory if you want its screenshots somewhere other than ignored `test-results`.

## Evaluation and remaining gaps

`python scripts/evaluate_standalone.py` generates temporary seed-42 fixtures and computes precision/recall/F1 from transaction/type pairs. It deliberately includes ambiguous small amount differences. Overall micro F1 is 0.885, but `FX_ROUNDING` F1 is only 0.571. A single overall score hides this weakness. No externally labelled dataset or operational workload has been evaluated. Duplicate occurrence retention has separate regression tests because the metric collapses repeated transaction/type labels.

Before real use, the priority gaps are tenant boundaries and role-based permissions, dataset/history retention, independent labelled evaluation, and worker recovery/monitoring. See [architecture](architecture.md) for algorithmic and execution limits, and [deployment](deployment.md) for hosting options.
