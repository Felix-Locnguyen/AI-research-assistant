from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_name: str = "Nexus AI"
    env: str = "development"
    database_url: str = ""   # T66: bắt buộc; fail-fast ở connection.py nếu trống
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""        # so sánh header X-Telegram-Bot-Api-Secret-Token
    zalo_oa_access_token: str = ""           # token Zalo OA — hết hạn sau ~1h, cập nhật thủ công
    zalo_webhook_secret: str = ""            # secret key OA để xác thực X-ZEvent-Signature
    messenger_page_access_token: str = ""
    messenger_app_secret: str = ""           # xác thực X-Hub-Signature-256
    messenger_verify_token: str = ""         # token cho bước xác minh webhook (GET)
    messenger_tag: str = "ACCOUNT_UPDATE"    # MESSAGE_TAG khi gửi chủ động ngoài cửa sổ 24h
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash"
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()