# WOR-61 Integration Review

Review date: 2026-09-05. This is an intermediate integration review, not the
Stage 3 acceptance report and not a real-model quality evaluation.

## GitHub synchronization

All three implementation heads were present on GitHub:

| Work | PR | Head at review |
| --- | --- | --- |
| Backend, WOR-63 | [#23](https://github.com/JichaoChen1123/RAGOps/pull/23) | `32c3d922a087772849a3c4c67b624830fe63fb26` |
| Frontend, WOR-64 | [#24](https://github.com/JichaoChen1123/RAGOps/pull/24) | `0515cfb3cb93203a8c2613741d8fc0125bbee04d` |
| QA fixtures/tests, WOR-65 | [#22](https://github.com/JichaoChen1123/RAGOps/pull/22) | `a693bdb28e3ac915e961747789aca36868cdd77d` |

PR #24 originally lacked a visible Multica issue association. Its title now
includes WOR-64 and the issue PR lookup returns it. This was not lost code.
Its repository-contract CI failure was an obsolete assertion that the overview
must contain hard-coded model/prompt names. The updated assertion checks the
current capability contract instead. PR #22's initial red tests were run against
the contract-only base; the combined implementation is the correct review target.

The three heads were merged locally without conflicts on an isolated review
branch. The delivery target is `work/wor-61-offline-readiness`, with
[draft PR #21](https://github.com/JichaoChen1123/RAGOps/pull/21) targeting main.
This review does not authorize a merge to main.

## Corrections Found During Integration

1. Removed the legacy job-path bypass of context provenance. Provided or
   legacy-unknown contexts do not receive retrieval-recall scores in new runs.
   Existing standalone evaluator oracle tests are retained; the old API fixture
   test now checks current-run semantics instead of treating historical labels
   as this run's output.
2. Corrected import error locations for schema versions, mixed version fields,
   context provenance and duplicate ranks. Unsupported versions now have the
   specified top-level error code. Database duplicate errors include row, field
   and sample ID while retaining the existing sample ID list.
3. Added a read-only legacy-run API projection with unknown model/mock/usage
   fields. Migration does not invent or persist a legacy run ID.
4. Preserved the already committed model answer and attempt history when later
   metric execution fails. The task still fails and quality remains unevaluated.
5. Resolved numeric citation positions back to private chunk IDs internally.
   Citation resolution never asserts semantic support.
6. Handled invalid response encoding, malformed optional finish reasons and
   non-finite Retry-After values. The production HTTP transport now cancels the
   whole attempt at its deadline, including a slow response body.
7. Updated the QA transport harness to use explicit injected test transport.
   Successful fake HTTP calls are correctly marked simulated and avoid TLS
   initialization affecting the 100ms synthetic timeout budget. Configuration
   and disabled-call rejection cases still use the fail-closed factory path.
8. Kept recent frontend task/report links visible even when no quality metrics
   have been evaluated.
9. Made the Windows PowerShell API script parse on PowerShell 5, added request
   timeouts and restart checks for run ID, answer and dataset hash. Corrected
   Docker-script parsing and explicitly forced mock execution/external calls off.

## Commands Actually Executed

Commands ran in an isolated checkout on Windows with Python 3.11.15.
The backend virtual environment was created with:

```powershell
uv sync --project backend --extra dev --frozen
npm.cmd --prefix frontend ci --no-audit --no-fund
```

Equivalent repository-relative commands and observed results:

| Command | Result |
| --- | --- |
| `backend/.venv/Scripts/ruff.exe check --config backend/pyproject.toml backend/app tests scripts` | Pass |
| `backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml tests/backend tests/evaluation -q --tb=short --cov=app --cov-branch --cov-report=term --cov-fail-under=85` | 109 passed; branch-inclusive coverage 90.69%; one Starlette deprecation warning |
| `npm.cmd --prefix frontend test -- --reporter=dot` | 41 passed in 5 files |
| `npm.cmd --prefix frontend run build` | Typecheck and production build passed |
| `backend/.venv/Scripts/python.exe scripts/validate_repository.py` | Pass |
| `tests/acceptance/validate-wor-49.ps1` | Pass, 15 interactions |
| `tests/acceptance/validate-wor-55.ps1` | Pass |
| `tests/acceptance/offline-readiness/validate-assets.ps1` | Pass, 3 v2 samples, 1 v1 sample, 9 invalid cases |
| `tests/acceptance/offline-readiness/run-local-restart.ps1 -Port 18015` | Pass before and after process restart |
| `docker compose config --quiet` | Pass |
| `docker info --format '{{json .ServerVersion}}'` | Fail: Docker Desktop Linux engine named pipe not found |

The local HTTP loop imported one artificial sample, published it, executed the
mock adapter and read its report/export. After restarting the backend, the same
dataset hash, job, run ID and generated answer were present. The mock run had
execution succeeded, quality not_evaluated, unknown verdict and null quality
score. Temporary local services were stopped after the test.

Initial integration had 93 passes and 10 failures; these failures were fixed and
the complete suite rerun. Additional review regressions raised the total to 109.
An initial PowerShell parse failure was also corrected and the local restart
script rerun successfully. Earlier sandbox permission errors are not counted
as functional failures or passes.

## Boundaries and Remaining Acceptance

| Area | Code implemented | Offline test passed | Real connection verified |
| --- | --- | --- | --- |
| Model contracts/mock/compatible adapter | Yes | Yes, injected responses only | No, prohibited this stage |
| Input/label isolation and run storage | Yes | Yes | Not applicable |
| Migration and old report reads | Yes | Yes, synthetic old database | Not evaluated on user production data |
| Frontend status/metrics/report mapping | Yes | 41 tests and build | Browser-to-backend cross-device E2E pending WOR-66 |
| Local HTTP and restart persistence | Yes | Yes, localhost + SQLite | No external model |
| Docker environment wiring | Yes | Configuration/parser checks only | Engine build/start/restart not run locally |
| Official Codex extension | Interface boundary only | No account integration attempted | No; Plus is not treated as general API credit |

WOR-66 still owns independent integrated browser acceptance, desktop/mobile
screenshots and final startup/configuration/upgrade documentation. The parent
stage remains in progress until those checks are reviewed. No real data was
downloaded, no account login was performed and no real model request was made.

Docker reproduction, after the user independently starts Docker Desktop:

```powershell
$env:RAGOPS_MODEL_EXECUTION_ADAPTER = 'mock'
$env:RAGOPS_MODEL_EXTERNAL_CALLS_ENABLED = 'false'
docker info
docker compose config --quiet
./tests/acceptance/offline-readiness/run-docker-loop.ps1
```

The Docker script creates an isolated project and removes only that project's
test containers/volumes. It uses ports 8000 and 5173; ensure they are free.
Without Docker, the already tested local alternative is:

```powershell
./tests/acceptance/offline-readiness/run-local-restart.ps1 -Port 18015
```
