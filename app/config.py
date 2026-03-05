"""
app/config.py
─────────────
Central settings loaded from environment variables / .env file.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Gemini
    #gemini_api_key: str = ""
    # GROQ
    groq_api_key: str = ""
    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5432/ai_news"

    # Email (Resend)
    resend_api_key: str = ""
    digest_recipient_email: str = ""
    digest_sender_email: str = "digest@yourdomain.com"

    # Scheduler
    digest_cron: str = "0 8 * * *"

    # Scraper
    scrape_window_hours: int = 24


settings = Settings()