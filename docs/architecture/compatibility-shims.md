# Compatibility shim retirement

Compatibility façades preserve the current public API while domain ownership is
migrated. They are transitional, not a second permanent API.

| Shim | Phase A (current) | Phase B | Phase C | Phase D |
| --- | --- | --- | --- | --- |
| `AiService` flat methods | all imports work; prompt methods delegate | routers use `service.prompts` | mark remaining flat prompt calls deprecated | remove prompt bridge |
| `OrchestrationService` | domain services plus fallback lookup work | routers depend on domain services | fail architecture tests on new fallback calls | remove `__getattr__` |
| project/task mixin façades | all current imports work | inject project/task services | deprecate cross-domain helpers | remove inherited façade |
| memory compatibility host | extracted domain modules delegate through host | routers inject memory domains | freeze host API | retain only a thin explicit façade |

Every migration keeps route paths and response models stable. Removal requires a
repository-wide import search, characterization tests, and a release note.
