"""Application settings (pydantic-settings). Env var name = upper-case attribute name.

DATABASE_URL and JWT_SECRET are REQUIRED (no default): importing this module without
them raises a pydantic ValidationError naming the missing variables (fail fast).
"""

from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEFAULT_FREE_EMAIL_DOMAINS = (
    "gmail.com,yahoo.com,yahoo.co.in,outlook.com,hotmail.com,live.com,rediffmail.com,"
    "aol.com,icloud.com,proton.me,protonmail.com,mail.com,gmx.com,yandex.com,zoho.com"
)


def _split_csv(value: object) -> object:
    """Accept 'a,b,c' (env style), a JSON-ish list, or an actual list."""
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("[") and text.endswith("]"):
            text = text[1:-1]
        return [p.strip().strip("\"'") for p in text.split(",") if p.strip().strip("\"'")]
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # --- required ---
    database_url: str
    jwt_secret: str

    # --- auth / tokens ---
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 30
    refresh_token_days: int = 7
    email_token_hours: int = 24
    reset_token_minutes: int = 60
    otp_ttl_minutes: int = 10
    otp_length: int = 6
    otp_max_attempts: int = 5
    invitation_expiry_days: int = 7
    # when true auth endpoints add devOtp / devToken to responses (dev only)
    expose_dev_codes: bool = False

    # --- web ---
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["*"])
    free_email_domains: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: DEFAULT_FREE_EMAIL_DOMAINS.split(",")
    )
    site_url: str = "http://localhost:8000"

    # --- uploads ---
    max_resume_mb: int = 5
    upload_dir: str = "uploads"
    max_image_mb: int = 2

    # --- jobs / credits ---
    job_expiry_days: int = 30
    default_job_quota: int = 10
    demo_credits: int = 50
    expiring_soon_days: int = 3
    unlock_credit_cost: int = 1
    invite_credit_cost: int = 2

    # --- rate limiting (requests per window per key) ---
    rate_limit_enabled: bool = True
    rate_limit_login: int = 30
    rate_limit_otp: int = 15
    rate_limit_search: int = 120
    rate_limit_window_seconds: int = 60

    # --- pagination ---
    max_page_size: int = 100
    default_page_size: int = 20

    # --- scheduler ---
    scheduler_enabled: bool = True
    scheduler_expiry_minutes: int = 60
    scheduler_alert_instant_minutes: int = 5

    # --- pluggable senders ("log" logs to stdout) ---
    email_sender: str = "log"
    otp_sender: str = "log"
    email_from: str = "no-reply@jobportal.demo"

    # --- misc ---
    log_level: str = "INFO"

    @field_validator("database_url")
    @classmethod
    def _normalise_database_url(cls, v: str) -> str:
        v = v.strip()
        if v.startswith("postgresql://"):
            return "postgresql+psycopg://" + v[len("postgresql://"):]
        if v.startswith("postgres://"):
            return "postgresql+psycopg://" + v[len("postgres://"):]
        return v

    @field_validator("cors_origins", "free_email_domains", mode="before")
    @classmethod
    def _parse_csv(cls, v: object) -> object:
        return _split_csv(v)

    @field_validator("free_email_domains")
    @classmethod
    def _lower_domains(cls, v: list[str]) -> list[str]:
        return [d.lower().lstrip("@") for d in v]

    @property
    def max_resume_bytes(self) -> int:
        return self.max_resume_mb * 1024 * 1024

    @property
    def max_image_bytes(self) -> int:
        return self.max_image_mb * 1024 * 1024


settings = Settings()
