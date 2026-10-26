from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from invoice_api.constants import RATE_LIMIT_MAX_WINDOW_MINUTES

# The value .env.example ships with: it is public, so it must never sign tokens.
SECRET_KEY_PLACEHOLDER = "generate-one-with-python-secrets-token_hex-32"
# token_hex(32) gives 64 characters; HS256 wants at least 32 bytes of key.
SECRET_KEY_MIN_LENGTH = 32


class Environment(StrEnum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # production hides the API docs, formats logs as JSON and refuses to seed demo data.
    ENVIRONMENT: Environment = Environment.DEVELOPMENT
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    @field_validator("SECRET_KEY")
    @classmethod
    def _secret_key_is_strong(cls, value: str) -> str:
        if value == SECRET_KEY_PLACEHOLDER or len(value) < SECRET_KEY_MIN_LENGTH:
            raise ValueError(
                f"SECRET_KEY must be at least {SECRET_KEY_MIN_LENGTH} characters and not "
                "the .env.example placeholder; generate one with "
                'python -c "import secrets; print(secrets.token_hex(32))"'
            )
        return value

    # LLM extraction. The key is optional so the app and the tests run without
    # it; the extraction service fails with a clear error if it is missing.
    ANTHROPIC_API_KEY: SecretStr | None = None
    LLM_MODEL: str = "claude-haiku-5-5"
    LLM_TIMEOUT_SECONDS: float = 30.0
    LLM_MAX_RETRIES: int = 2
    LLM_MAX_OUTPUT_TOKENS: int = 1024
    # Model calls in flight at once, per process. Past it, extraction answers 503.
    LLM_MAX_CONCURRENT_CALLS: int = Field(20, ge=1)
    MAX_INVOICE_TEXT_CHARS: int = 20_000
    LLM_INPUT_PRICE_PER_MTOK: Decimal = Decimal("0.10")
    LLM_OUTPUT_PRICE_PER_MTOK: Decimal = Decimal("0.50")

    # Spending limits, in USD and on the estimated cost stored in llm_calls. A
    # day is a UTC calendar day. The extraction that crosses the limit is still
    # served, so the real spending can exceed it by one extraction.
    # The global one protects the money, not the availability: whoever registers
    # GLOBAL / USER accounts can exhaust it for everybody. Keep that ratio high
    # (tests/test_config.py), and the user budget big enough for real use.
    USER_DAILY_BUDGET_USD: Decimal = Decimal("0.05")
    GLOBAL_DAILY_BUDGET_USD: Decimal = Decimal("5.00")

    # Abuse limits of the auth endpoints, counted per client IP.
    LOGIN_MAX_FAILURES_PER_IP_AND_EMAIL: int = 5
    LOGIN_MAX_FAILURES_PER_IP: int = 20
    LOGIN_WINDOW_MINUTES: int = Field(15, ge=1, le=RATE_LIMIT_MAX_WINDOW_MINUTES)
    REGISTER_MAX_PER_IP: int = 5
    REGISTER_WINDOW_MINUTES: int = Field(60, ge=1, le=RATE_LIMIT_MAX_WINDOW_MINUTES)


settings = Settings()  # type: ignore
