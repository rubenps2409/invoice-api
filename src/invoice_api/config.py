from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # ignore other environment variables than database_url
    )

    DATABASE_URL: str


settings = Settings()  #type: ignore
