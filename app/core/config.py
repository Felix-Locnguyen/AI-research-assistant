from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_name: str = "Nexus AI"
    env: str = "development"
    database_url: str = "postgresql+asyncpg://postgres:123456@localhost:5432/nexus_ai"
    telegram_bot_token: str = ""
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash"
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()