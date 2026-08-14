# External call inventory

This is the checked-in inventory for outbound calls in the runtime application. Every new integration must add an entry here and use the shared timeout, correlation, and lifecycle policy.

| Runtime path | Transport | Timeout | Retry / idempotency | Cancellation and shutdown | Telemetry / sensitive-data rule |
| --- | --- | --- | --- | --- | --- |
| `backend/core/http_clients.py` and provider/GitHub adapters using `managed_http_client` | pooled `httpx.AsyncClient` | `external_timeout()` gives bounded connect, pool, read, write, and total phases; provider-specific caps come from settings | `external_retry_policy()`: safe methods may retry transient statuses; writes require an idempotency key, otherwise one attempt | request cancellation propagates through `httpx`; shared clients close on application/worker shutdown | record purpose, status, duration, and request/correlation IDs; never log auth headers, tokens, prompts, or response bodies |
| `backend/modules/orchestration/local_runtime.py:_health_ok` | pooled `httpx` | 2 seconds | health GET is retryable by caller polling; no write retry | task cancellation propagates; worker shutdown closes the pool | log provider ID and status only; health URL may be logged, credentials may not |
| `backend/workers/email.py:send_email` | `aiosmtplib` SMTP | `settings.SMTP_TIMEOUT_SECONDS` | no automatic retry in the request process; Celery delivery is the durable retry boundary and must remain idempotent for the recipient/message | `await` is cancellable; Celery task shutdown/revocation must propagate cancellation | log recipient only in redacted/operational form; never log tokens, message bodies, or SMTP credentials |
| `backend/core/cache.py` | Redis async client | Redis client timeout/settings; cache reads are fail-open | cache writes are best effort; no retry for non-idempotent invalidation sequences | cache operations are bounded and may be cancelled; close Redis during application shutdown | cache metrics use fixed operation labels; keys and values are not logged |
| `backend/core/storage.py` | boto3/S3-compatible storage | provider/client configuration; callers must supply bounded operation timeouts | object reads are safe to retry; writes require object-key idempotency and provider retry policy | blocking SDK calls must stay off the event loop; shutdown waits for owned executor work | log bucket-independent operation metadata; never object contents, signed URLs, or credentials |
| `backend/modules/orchestration/local_repo.py` and `execution/cpu_executor.py` | `subprocess.run` / `Popen` | explicit per-command timeout; local runtime startup has a bounded health deadline | no blind retry; caller decides whether a command is idempotent | timeout kills/terminates the process; worker shutdown reaps managed processes | command arguments are allowlisted and sensitive values must be redacted before logging |
| `backend/tools/phase0_baseline.py`, `backend/tools/phase7_validation.py` | diagnostic-only `httpx`, Redis, asyncpg, subprocess | CLI/configurable bounded probe timeouts | probes never retry writes; repeated reads are bounded by the requested sample count | probe cancellation exits without mutating application state | output is a measurement artifact; do not include secrets or response bodies |

## Enforcement

- Runtime HTTP clients are centralized in `backend/core/http_clients.py`; direct `httpx.AsyncClient` construction is permitted there and in tests/tools only.
- `backend/core/external_http.py` is the policy source for timeout construction, safe correlation headers, and retry classification.
- External calls must expose a bounded timeout, preserve cancellation, and emit duration/error telemetry. A retry must state why duplicate delivery is safe.
- Calls that cannot be made async must be isolated from the event loop and documented with their shutdown behavior.
- This inventory is reviewed whenever a provider, storage backend, worker integration, or diagnostic probe is added.
- Action-level side effects, idempotency contracts, and autonomous-use blocks are documented in [EXTERNAL_EFFECT_IDEMPOTENCY_INVENTORY.md](./EXTERNAL_EFFECT_IDEMPOTENCY_INVENTORY.md).
