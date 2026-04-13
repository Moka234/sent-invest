from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# __file__ = .../backend/app/core/settings.py
# parents[3] = .../sent-invest (项目根目录)
BASE_DIR = Path(__file__).resolve().parents[3]
ENV_FILE = BASE_DIR / ".env"


class Settings(BaseSettings):
    database_url: str

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
