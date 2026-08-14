# Performance baselines

Repeatable latency and query-count snapshots for the hottest backend paths.

## Quick start (HTTP only)

From the repository root with the API running:

```bash
python backend/tools/phase0_baseline.py \
  --url http://127.0.0.1:8000/health/live \
  --url http://127.0.0.1:8000/health/ready \
  --output artifacts/phase0-baseline.json
```

Optional authenticated control-plane sampling (requires session cookie or gateway):

```bash
python backend/tools/phase0_baseline.py \
  --url http://127.0.0.1:8000/api/v1/orchestration/portfolio/control-plane \
  --requests 10 \
  --concurrency 2
```

## In-process hot paths

Requires `DATABASE_URL` and an owner with orchestrator projects:

```bash
export BENCHMARK_OWNER_ID="<user-uuid>"
python backend/tools/phase0_baseline.py \
  --in-process \
  --samples 5 \
  --output artifacts/performance-baseline.json
```

Benchmarks captured:

| Name | What it measures |
|------|------------------|
| `portfolio_control_plane` | `load_portfolio_control_plane_bundle` wall time + SQL count |
| `semantic_vector_search` | pgvector retrieval when embeddings exist (skipped otherwise) |
| `run_claim_precheck` | `get_run_for_worker` + claim gate |

## Regression gate (optional CI / nightly)

Compare current p95 against a checked-in or prior artifact; fail when >2× slower:

```bash
python backend/tools/phase0_baseline.py \
  --in-process \
  --owner-id "$BENCHMARK_OWNER_ID" \
  --compare artifacts/performance-baseline.json \
  --fail-on-regression \
  --output artifacts/performance-baseline-latest.json
```

## Pytest smoke tests

```bash
cd backend
PYTHONPATH=.. pytest tests/test_performance_harness.py -q
```

Integration case uses the shared `tenant_pair` fixture when PostgreSQL is reachable.

## Artifact schema

Reports use `schema_version: 2` with sections:

- `endpoints` — HTTP latency samples
- `in_process.benchmarks` — repository hot paths
- `regression` — output when `--compare` is set
