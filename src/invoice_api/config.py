from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # el .env tiene variables que solo usa Docker Compose
    )

    DATABASE_URL: str


settings = Settings()  #type: ignore
