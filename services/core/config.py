"""
Alpine ERP — Application Configuration
───────────────────────────────────────
GbilConfig subclass. Provides a typed view of app-level env vars
used in lifespan (logger + realtime setup).
"""

from gbil.config import GbilConfig
from pydantic import Field


class AppConfig(GbilConfig):
    SERVICE_NAME: str = Field(default="alpine-erp-core")
    ENVIRONMENT: str = Field(default="development")
    LOG_LEVEL: str = Field(default="INFO")


def get_config() -> AppConfig:
    return AppConfig.load()
