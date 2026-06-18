import json
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_CONFIG_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _CONFIG_DIR.parent
_REPO_DIR = _BACKEND_DIR.parent
# Canonical path for code that reads/writes .env on disk (settings UI, etc.).
ENV_FILE = _BACKEND_DIR / ".env"
# Pydantic loads in order; later files override (repo-root `.env` wins over `backend/.env`).
_ENV_FILES_FOR_PYDANTIC: tuple[str, ...] = tuple(
    str(p) for p in (_BACKEND_DIR / ".env", _REPO_DIR / ".env") if p.is_file()
)
_SETTINGS_CONFIG_KWARGS: dict[str, Any] = {
    "env_file_encoding": "utf-8",
    "case_sensitive": False,
    "extra": "ignore",
    "env_ignore_empty": True,
}
if _ENV_FILES_FOR_PYDANTIC:
    _SETTINGS_CONFIG_KWARGS["env_file"] = _ENV_FILES_FOR_PYDANTIC


class Settings(BaseSettings):
    model_config = SettingsConfigDict(**_SETTINGS_CONFIG_KWARGS)
    APP_NAME: str = "fullstack-app"
    APP_ENV: str = "dev"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    LOG_LEVEL: str = "INFO"
    CORE_DOMAIN_SINGULAR: str = "Project"
    CORE_DOMAIN_PLURAL: str = "Projects"
    PLATFORM_DEFAULT_MODULE_PACK: str = "full_platform"

    DATABASE_URL: str
    DATABASE_POOL_SIZE: int = 5
    DATABASE_MAX_OVERFLOW: int = 10
    DATABASE_POOL_RECYCLE_SECONDS: int = 1800
    DATABASE_POOL_TIMEOUT_SECONDS: int = 30
    REDIS_URL: str
    CELERY_BROKER_URL: str = ""
    CELERY_RESULT_BACKEND: str = ""
    CELERY_TASK_ALWAYS_EAGER: bool = False
    CELERY_TASK_DEFAULT_QUEUE: str = "default"
    CELERY_EMAIL_QUEUE: str = "email"
    # Logical service boundaries: separate broker queues + worker processes (ADR 0006).
    CELERY_QUEUE_GITHUB: str = "github"
    CELERY_QUEUE_MODEL_GATEWAY: str = "model_gateway"
    CELERY_QUEUE_OBSERVABILITY: str = "observability"
    CELERY_QUEUE_CPU: str = "cpu"
    CELERY_RESULT_EXPIRES_SECONDS: int = 3600
    PROVIDER_HEALTHCHECK_INTERVAL_MINUTES: int = 5
    GITHUB_ISSUE_POLL_INTERVAL_MINUTES: int = 15
    # Run event query bounds (orchestration snapshots, API, replay, classifier).
    RUN_EVENTS_DEFAULT_LIMIT: int = 200
    RUN_EVENTS_MAX_LIMIT: int = 1000
    RUN_EVENTS_REPLAY_MAX: int = 2000
    RUN_EVENTS_CLASSIFIER_MAX: int = 400
    RUN_EVENTS_EXPLAIN_MAX: int = 500
    AI_RETRIEVE_CHUNK_SCAN_MAX: int = 500
    ORCHESTRATION_LIST_TASKS_DEFAULT_LIMIT: int = 500
    ORCHESTRATION_LIST_TASKS_MAX_LIMIT: int = 5000
    ORCHESTRATION_LIST_RUNS_DEFAULT_LIMIT: int = 500
    ORCHESTRATION_LIST_RUNS_MAX_LIMIT: int = 5000
    ORCHESTRATION_LIST_DOCUMENTS_DEFAULT_LIMIT: int = 200
    ORCHESTRATION_LIST_DOCUMENTS_MAX_LIMIT: int = 2000

    ORCHESTRATION_RUN_RATE_LIMIT_PER_MINUTE: int = 120
    ORCHESTRATION_SLA_SCAN_INTERVAL_MINUTES: int = 20
    AGENT_TOKEN_BUDGET_WINDOW_DAYS: int = 30
    # When false, model-level failover inside a single provider call is disabled (service-level candidate loop may still apply).
    ORCHESTRATION_PROVIDER_FAILOVER: bool = True
    # When true, execute_run routes run modes through a LangGraph StateGraph (see langgraph_runner).
    ORCHESTRATION_USE_LANGGRAPH: bool = False
    # Durable enqueue backend label (future: temporal). Celery is the only implementation today.
    ORCHESTRATION_DURABLE_QUEUE_BACKEND: str = "celery"
    ORCHESTRATION_CPU_JOB_TIMEOUT_SECONDS: int | None = None
    ORCHESTRATION_CPU_REQUIRE_DOCKER: bool | None = None

    JWT_SECRET: str
    JWT_ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    REFRESH_TOKEN_EXPIRE_DAYS: int

    FRONTEND_URL: str = "http://localhost:5173"
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: str = "lax"
    COOKIE_DOMAIN: str | None = None
    ADMIN_SIGNUP_INVITE_CODE: str = ""
    ACCESS_COOKIE_NAME: str = "access_token"
    REFRESH_COOKIE_NAME: str = "refresh_token"
    CSRF_COOKIE_NAME: str = "csrf_token"
    CSRF_HEADER_NAME: str = "X-CSRF-Token"
    PUBLIC_RATE_LIMIT_REQUESTS: int = 120
    PUBLIC_RATE_LIMIT_WINDOW_SECONDS: int = 60
    AUTH_FAILURE_LIMIT: int = 8
    AUTH_FAILURE_WINDOW_SECONDS: int = 900
    CACHE_ENABLED: bool = True
    CACHE_SESSION_TTL_SECONDS: int = 60
    CACHE_EMBEDDING_TTL_SECONDS: int = 86400
    CACHE_RAG_RETRIEVAL_TTL_SECONDS: int = 300
    CACHE_ACL_TTL_SECONDS: int = 300
    CACHE_ACL_DENIED_TTL_SECONDS: int = 60
    CACHE_PLATFORM_METADATA_TTL_SECONDS: int = 1800
    CACHE_MEMORY_SETTINGS_TTL_SECONDS: int = 300
    CACHE_HTTP_DOCUMENT_LIST_MAX_AGE_SECONDS: int = 60
    HEALTH_READY_PUBLIC: bool = False
    HEALTH_VERSION_PUBLIC: bool = False
    REQUIRE_EMAIL_VERIFICATION: bool = True

    # Email verification / password reset token TTLs (seconds)
    VERIFICATION_TOKEN_TTL: int = 86400   # 24 h
    PASSWORD_RESET_TOKEN_TTL: int = 3600  # 1 h

    # SMTP — leave empty to skip sending (useful in dev)
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "noreply@example.com"
    SMTP_TLS: bool = True

    # Observability
    SENTRY_DSN: str = ""
    SENTRY_TRACES_SAMPLE_RATE: float = 0.2
    OTLP_ENDPOINT: str = ""   # e.g. http://localhost:4317
    OTLP_INSECURE: bool = True

    # Object storage (S3-compatible, e.g. AWS S3 or MinIO)
    STORAGE_BUCKET: str = ""
    STORAGE_REGION: str = "us-east-1"
    STORAGE_ENDPOINT_URL: str = ""
    STORAGE_ACCESS_KEY: str = ""
    STORAGE_SECRET_KEY: str = ""
    STORAGE_USE_SSL: bool = False
    STORAGE_FORCE_PATH_STYLE: bool = True
    STORAGE_PUBLIC_BASE_URL: str = ""
    STORAGE_AUTO_CREATE_BUCKET: bool = True
    STORAGE_PUBLIC_READ: bool = True
    STORAGE_AVATAR_MAX_BYTES: int = 5 * 1024 * 1024

    AI_DEFAULT_PROVIDER: str = "local"
    AI_EMBEDDING_PROVIDER: str = "local"
    AI_LOCAL_MODEL_NAME: str = "local-heuristic"
    AI_DOCUMENT_MAX_BYTES: int = 1024 * 1024
    AI_DOCUMENT_CHUNK_SIZE: int = 1200
    AI_DOCUMENT_CHUNK_OVERLAP: int = 150
    AI_DOCUMENT_INGEST_ASYNC: bool = True
    AI_MAX_OUTPUT_TOKENS: int = 1024
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_DEFAULT_MODEL: str = "gpt-4.1-mini"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_BASE_URL: str = "https://api.anthropic.com/v1"
    ANTHROPIC_DEFAULT_MODEL: str = "claude-3-5-sonnet-latest"
    GITHUB_APP_ID: str = ""
    GITHUB_APP_SLUG: str = ""
    GITHUB_APP_PRIVATE_KEY: str = ""
    GITHUB_APP_WEBHOOK_SECRET: str = ""
    GITHUB_APP_CLIENT_ID: str = ""
    GITHUB_APP_CLIENT_SECRET: str = ""
    GITHUB_APP_NAME: str = "Troop GitHub App"

    # AI memory layer (mem0-inspired facade over semantic memory)
    MEMORY_LAYER_ENABLED: bool = True
    MEMORY_PROVIDER: str = "semantic_pgvector"
    MEMORY_DEFAULT_SEARCH_LIMIT: int = 5
    MEMORY_EXTRACTION_ENABLED: bool = True
    MEMORY_LLM_EXTRACTION_ENABLED: bool = False
    MEMORY_DEDUP_ENABLED: bool = True
    MEMORY_MIN_EXTRACTION_CONFIDENCE: float = 0.45
    MEMORY_LOG_CONTENT_IN_DEV: bool = False

    # RAG layer (LangChain-inspired facade over project documents + pgvector)
    RAG_ENABLED: bool = True
    RAG_PROVIDER: str = "native"
    RAG_VECTOR_STORE: str = "pgvector"
    RAG_EMBEDDING_PROVIDER: str = ""
    RAG_EMBEDDING_MODEL: str = ""
    RAG_CHUNK_SIZE: int = 0
    RAG_CHUNK_OVERLAP: int = 0
    RAG_TOP_K: int = 5
    RAG_SCORE_THRESHOLD: float = 0.2
    RAG_SCORE_THRESHOLD_LOCAL: float = 0.05
    RAG_RERANK_ENABLED: bool = False
    RAG_MAX_CONTEXT_TOKENS: int = 4000
    RAG_INDEXING_BATCH_SIZE: int = 64
    RAG_LOG_CONTENT_IN_DEV: bool = False
    RAG_CHUNK_FALLBACK_MAX: int = 200
    RAG_PYTHON_FALLBACK_ENABLED: bool = False
    AI_RETRIEVE_PYTHON_FALLBACK_ENABLED: bool = False
    RAG_ANSWER_TIMEOUT_SECONDS: int = 90
    RAG_BULK_INGEST_CONCURRENCY: int = 4
    MEMORY_INGEST_JOB_CONCURRENCY: int = 3

    CORS_ALLOWED_ORIGINS: list[str] = Field(default_factory=list)


    @property
    def celery_broker_url(self) -> str:
        return self.CELERY_BROKER_URL or self.REDIS_URL

    @property
    def celery_result_backend(self) -> str:
        return self.CELERY_RESULT_BACKEND or self.REDIS_URL

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() == "production"

    @property
    def orchestration_cpu_require_docker(self) -> bool:
        if self.ORCHESTRATION_CPU_REQUIRE_DOCKER is not None:
            return self.ORCHESTRATION_CPU_REQUIRE_DOCKER
        return self.is_production

    @property
    def allowed_origins(self) -> list[str]:
        return self.CORS_ALLOWED_ORIGINS or [self.FRONTEND_URL]

    @property
    def content_security_policy(self) -> str:
        connect_src = " ".join(dict.fromkeys(["'self'", *self.allowed_origins]))
        return (
            "default-src 'self'; "
            f"connect-src {connect_src}; "
            "img-src 'self' data: blob:; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; "
            "base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        )

    @field_validator("COOKIE_SAMESITE")
    @classmethod
    def validate_cookie_samesite(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in {"lax", "strict", "none"}:
            raise ValueError("COOKIE_SAMESITE must be one of: lax, strict, none")
        return normalized

    @field_validator("JWT_SECRET")
    @classmethod
    def validate_jwt_secret(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 32 or stripped.lower() in {"replace-me", "changeme", "secret"}:
            raise ValueError("JWT_SECRET must be a high-entropy secret with at least 32 characters")
        return stripped

    @field_validator("ACCESS_TOKEN_EXPIRE_MINUTES")
    @classmethod
    def validate_access_ttl(cls, value: int) -> int:
        if value <= 0 or value > 30:
            raise ValueError("ACCESS_TOKEN_EXPIRE_MINUTES must be between 1 and 30")
        return value

    @field_validator("REFRESH_TOKEN_EXPIRE_DAYS")
    @classmethod
    def validate_refresh_ttl(cls, value: int) -> int:
        if value <= 0 or value > 30:
            raise ValueError("REFRESH_TOKEN_EXPIRE_DAYS must be between 1 and 30")
        return value

    @field_validator("CORS_ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_cors_allowed_origins(cls, value):
        if value in (None, ""):
            return []
        if isinstance(value, str):
            normalized = value.strip()
            if normalized.startswith(("'", '"')) and normalized.endswith(("'", '"')):
                normalized = normalized[1:-1].strip()
            if normalized.startswith("["):
                parsed = json.loads(normalized)
                if not isinstance(parsed, list):
                    raise ValueError(
                    "CORS_ALLOWED_ORIGINS must be a list or comma-separated string"
                )
                return [str(item).strip() for item in parsed if str(item).strip()]
            return [item.strip() for item in normalized.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def validate_security_posture(self):
        if self.COOKIE_SAMESITE == "none" and not self.COOKIE_SECURE:
            raise ValueError("COOKIE_SECURE must be true when COOKIE_SAMESITE is 'none'")
        if self.is_production and not self.COOKIE_SECURE:
            raise ValueError("COOKIE_SECURE must be enabled in production")
        if self.is_production and any(
            origin.startswith("http://") for origin in self.allowed_origins
        ):
            raise ValueError("CORS_ALLOWED_ORIGINS/FRONTEND_URL must use https in production")
        if self.is_production and self.ORCHESTRATION_RUN_RATE_LIMIT_PER_MINUTE <= 0:
            raise ValueError(
                "ORCHESTRATION_RUN_RATE_LIMIT_PER_MINUTE must be > 0 in production "
                "(dev-only bypass requires APP_ENV=dev)"
            )
        return self


settings = Settings()
