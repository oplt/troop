# Latency service objectives

These are the initial production budgets for Troop. Evaluate them over a rolling 30-day window and alert on a sustained 10-minute or 15-minute window, not on individual requests.

| User journey | Objective | Indicator | Exclusions |
| --- | ---: | --- | --- |
| Simple API read | p95 < 250 ms | `troop_http_request_duration_seconds` for ordinary GET routes | streaming responses and model generation routes |
| Project detail | p95 < 500 ms | project-detail GET route duration | live SSE stream lifetime |
| Vector retrieval | p95 < 500 ms | `troop_rag_retrieval_duration_seconds{stage="vector_search"}` | embedding and generation provider time |
| UI navigation feedback | < 100 ms | local tab/route interaction to visible pending or rendered state | network completion |
| Initial page requests | no avoidable critical waterfall | Playwright request baseline | lazy user-initiated tab requests |

Provider work is reported separately through `troop_provider_request_duration_seconds`; embedding is reported through `troop_embedding_duration_seconds`. An API request that waits for model generation will still have a long end-to-end duration, but dashboards must display the provider span beside it rather than treating the duration as ordinary application latency.

## Simple API reads

If the budget burns, group by `route`, then compare database duration and query count. Check for a collection scan, missing cursor, or hidden remote call before increasing the target.

## Project detail

Inspect the project-detail request waterfall and slow SQL. Keep optional tabs lazy and use the live snapshot channel for active state instead of multiplying polling requests.

## Vector retrieval

This stage begins after the query embedding is available and ends when vector candidates return. Check pgvector indexes, candidate limits, database pool saturation, and cache hit rate. Embedding latency has its own metric and must not be added to this budget.

## RAG degraded mode

Production deployments do not scan the document corpus in Python unless
`RAG_ALLOW_PYTHON_FALLBACK_IN_PRODUCTION` is explicitly enabled for a small or
migration-recovery installation. Any vector-store failure increments
`troop_rag_degraded_total`; investigate PostgreSQL/pgvector health before enabling
the bounded fallback.

## UI navigation

Every navigation should synchronously expose the selected state or a stable skeleton within 100 ms. Capture the request count with `pnpm baseline:requests`; regressions should fail review when a page adds an avoidable critical request waterfall.
