from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # .env also holds the POSTGRES_* vars used by Docker Compose
    )

    DATABASE_URL: str


settings = Settings()  # type: ignore
