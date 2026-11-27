# photo-analysis API autotests

[![API autotests](https://github.com/marimirals/photo-analysis-autotests/actions/workflows/autotests.yml/badge.svg)](https://github.com/marimirals/photo-analysis-autotests/actions/workflows/autotests.yml)

Automated API tests for [photo-analysis](https://github.com/marimirals/photo-analysis) — a service that stores photos and analyzes them asynchronously (Go, Kafka, gRPC, Python, PostgreSQL, S3).

**[Latest Allure report](https://marimirals.github.io/photo-analysis-autotests/)**

![Allure report](docs/allure-overview.png)
![Test details](docs/allure-test.png)

## What is covered

73 tests based on the [test plan](docs/test-plan.md):

| Area | Tests | Examples |
|---|---|---|
| Smoke | 3 | health and readiness, upload works |
| Positive scenarios | 11 | JPEG/PNG/WebP upload, byte-exact download, pagination, delete |
| Errors and boundary values | 41 | exactly 20 MB vs 20 MB + 1 byte, wrong file types, invalid `X-User-ID`, other user's photos (404, nothing deleted), invalid filters |
| Asynchronous analysis | 9 | blurred / dark images detected, resized copy found as duplicate (only within one user), re-analysis, filters by analysis results |
| Contract | 4 | every response is checked against the service's own OpenAPI spec: documented status codes, required fields, types, no undocumented fields |
| Database (SQL) | 5 | outbox event written and sent, analysis stored as returned by API, cascade delete, test data prepared with SQL |

**Found defect:** invalid `limit` / `offset` are silently accepted instead of `400` — [photo-analysis#1](https://github.com/marimirals/photo-analysis/issues/1). Covered by `xfail(strict=True)` tests that will start failing once the bug is fixed, as a reminder to remove the mark.

## How it works

- **API client** (`framework/api_client.py`) — tests call `api.upload(...)`, not raw URLs; every request and response is attached to the Allure report.
- **Isolation** — each test gets its own user (`X-User-ID`) and deletes what it uploaded, so tests do not affect each other and can run in any order.
- **Generated test data** (`framework/images.py`) — sharp, blurred, dark and resized images are generated in code with known properties.
- **No sleeps** — asynchronous results are awaited by polling with a timeout.
- **Contract checks** (`framework/contract.py`) — the OpenAPI spec is downloaded from the running service and converted to JSON Schema.
- **Gray box** (`framework/db.py`) — selected checks read PostgreSQL directly; parameters are always passed separately from SQL.

## Tech stack

Python, pytest, requests, jsonschema, psycopg, Pillow, Allure, Docker Compose, GitHub Actions.

## Run locally

Requirements: Docker, Python 3.12+, Node.js 20+ (for the report). The service repository must be next to this one (`../photo-analysis`) or set `PHOTO_ANALYSIS_DIR`.

```bash
docker compose up -d --build                 # test stand: the whole service in containers, clean DB
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt

export BASE_URL=http://localhost:18080       # PowerShell: $env:BASE_URL="http://localhost:18080"
export DB_DSN=postgresql://photo:photo@localhost:15433/photo
pytest                                       # all tests
pytest -m smoke                              # only smoke
pytest -m "not slow"                         # skip tests that wait for analysis

npx allure generate ./allure-results --clean && npx allure open ./allure-report
docker compose down -v
```

## CI

GitHub Actions runs on every push and pull request, nightly and on demand: builds the service from its repository, starts the stand, runs smoke tests and then the full suite, saves the Allure report and service logs as artifacts and publishes the report to GitHub Pages.

## Project structure

```
framework/   API client, contract checks, DB access, test images, waiters
tests/       test modules and fixtures (conftest.py)
docs/        test plan
.github/     CI workflow
docker-compose.yml   test stand
```