from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


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


settings = Settings()  # type: ignore
