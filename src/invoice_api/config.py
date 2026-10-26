from decimal import Decimal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from invoice_api.constants import RATE_LIMIT_MAX_WINDOW_MINUTES


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # LLM extraction. The key is optional so the app and the tests run without
    # it; the extraction service fails with a clear error if it is missing.
    ANTHROPIC_API_KEY: SecretStr | None = None
    LLM_MODEL: str = "claude-haiku-5-5"
    LLM_TIMEOUT_SECONDS: float = 30.0
    LLM_MAX_RETRIES: int = 2
    LLM_MAX_OUTPUT_TOKENS: int = 1024
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
