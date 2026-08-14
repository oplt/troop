# Observability metrics

Troop exposes Prometheus-compatible metrics at `GET /metrics` (see `modules/observability/metrics.py`).

## AI usage dashboards

### LLM attempts

```
troop_llm_attempts_total{purpose, provider, result}
```

- **purpose** — routing purpose (`agent_plan`, `final_answer`, …) or `direct` for non-routing `execute_prompt` callers
- **provider** — provider type slug (`openai_compatible`, `ollama`, `local-heuristic`, …)
- **result** — `success`, `error`, or `budget_exhausted`

Example PromQL — attempt error rate by purpose:

```promql
sum(rate(troop_llm_attempts_total{result="error"}[5m])) by (purpose)
/
sum(rate(troop_llm_attempts_total[5m])) by (purpose)
```

### LLM cost (estimated)

```
troop_llm_cost_micros_total{purpose, provider}
```

Micro-dollars (1 USD = 1_000_000 micros). Uses `ai/gateway/pricing.estimate_cost_micros`.

Example — hourly spend by provider:

```promql
sum(increase(troop_llm_cost_micros_total[1h])) by (provider) / 1e6
```

### Embedding tokens

```
troop_embed_tokens_total{provider, outcome}
```

Counts estimated input tokens for uncached embedding API batches (`estimate_tokens` heuristic).

## Grafana starter panels

1. **LLM attempt storm** — `sum(rate(troop_llm_attempts_total[5m])) by (purpose, result)` stacked area
2. **Budget pressure** — `sum(rate(troop_llm_attempts_total{result="budget_exhausted"}[15m]))`
3. **Estimated LLM spend** — `sum(increase(troop_llm_cost_micros_total[24h])) / 1e6` stat + by-provider pie
4. **Embed volume** — `sum(rate(troop_embed_tokens_total[5m])) by (provider)`

## Local scrape

```bash
curl -s http://127.0.0.1:8000/metrics | rg 'troop_llm_|troop_embed_'
```

Run a routed task or embedding job, then re-scrape to confirm counters move.

## Operational alerts (runs, queues, DB pool)

Enable scrape-time refresh with `METRICS_QUEUE_REFRESH_ENABLED=true` (also refreshes run status + pool gauges).

### Active runs

```
troop_orchestration_runs_active{status}
troop_orchestration_stale_in_progress_runs
troop_orchestration_oldest_in_progress_age_seconds
```

- **stale_in_progress** — runs in `in_progress` longer than `ORCHESTRATION_STALE_IN_PROGRESS_SECONDS`
- **oldest_in_progress_age_seconds** — age of the longest-running active run

Example alert — stuck runs:

```promql
troop_orchestration_stale_in_progress_runs > 0
```

### Celery / durable queue depth

```
troop_queue_depth{queue}
troop_queue_oldest_age_seconds{queue}
```

Queues sampled: `default`, `github`, `model_gateway`, `observability`, `cpu`, `integrations`, `email`.

Example — backlog growth:

```promql
troop_queue_depth{queue="default"} > 50
```

### Database pool saturation

```
troop_db_pool_checked_out{role}
troop_db_pool_overflow{role}
troop_db_pool_size{role}
troop_db_pool_checkout_wait_seconds_bucket{role}
```

Example — pool exhaustion pressure:

```promql
troop_db_pool_checked_out / troop_db_pool_size > 0.9
```

Checkout wait histogram is recorded on API `get_db()` session acquisition.

## Local scrape (operational)

```bash
curl -s http://127.0.0.1:8000/metrics | rg 'troop_orchestration_|troop_queue_|troop_db_pool_'
```

