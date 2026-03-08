from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    app_name: str = "Imobiliária IA Platform"
    app_version: str = "1.0.0"

    # Anthropic
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-6"

    # Database
    database_url: str = "sqlite:///./imobiliaria.db"

    # WhatsApp (Evolution API ou Z-API)
    whatsapp_api_url: str = ""
    whatsapp_api_token: str = ""
    whatsapp_instance: str = ""

    # Twilio (ligações)
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""

    # Scraping delay (segundos entre requests)
    scraping_delay: float = 2.0

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
