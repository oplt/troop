import json
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_ignore_empty=True,
    )
    APP_NAME: str = "fullstack-app"
    APP_ENV: str = "dev"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    LOG_LEVEL: str = "INFO"
    CORE_DOMAIN_SINGULAR: str = "Project"
    CORE_DOMAIN_PLURAL: str = "Projects"
    PLATFORM_DEFAULT_MODULE_PACK: str = "full_platform"

    DATABASE_URL: str
    REDIS_URL: str
    CELERY_BROKER_URL: str = ""
    CELERY_RESULT_BACKEND: str = ""
    CELERY_TASK_ALWAYS_EAGER: bool = False
    CELERY_TASK_DEFAULT_QUEUE: str = "default"
    CELERY_EMAIL_QUEUE: str = "email"
    CELERY_RESULT_EXPIRES_SECONDS: int = 3600

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
    AI_MAX_OUTPUT_TOKENS: int = 1024
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_DEFAULT_MODEL: str = "gpt-4.1-mini"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_BASE_URL: str = "https://api.anthropic.com/v1"
    ANTHROPIC_DEFAULT_MODEL: str = "claude-3-5-sonnet-latest"

    CORS_ALLOWED_ORIGINS: Annotated[list[str], NoDecode] = Field(default_factory=list)

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
        return self


settings = Settings()
