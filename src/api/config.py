from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="SEISMIK_",
        case_sensitive=False,
        extra="ignore",
    )

    environment: str = "development"
    redis_url: str = "redis://localhost:6379/0"
    webhook_hmac_secret: SecretStr = SecretStr("change-me-webhook")
    webhook_max_skew_seconds: int = Field(default=30, ge=5, le=300)
    webhook_idempotency_seconds: int = Field(default=600, ge=60)
    device_api_key: SecretStr = SecretStr("change-me-device-api-key")
    crowd_master_secret: SecretStr = SecretStr("change-me-crowd-secret")

    candidate_stream: str = "stream:seismik:candidates"
    official_stream: str = "stream:seismik:official"
    felt_reports_stream: str = "stream:seismik:felt-reports"
    damage_reports_stream: str = "stream:seismik:damage-reports"
    stream_maxlen: int = Field(default=100_000, ge=1_000)
    dispatcher_group: str = "push-dispatchers"
    consumer_name: str = "dispatcher-1"
    consumer_block_ms: int = Field(default=1_000, ge=10, le=60_000)
    pending_claim_idle_ms: int = Field(default=30_000, ge=1_000)
    max_delivery_attempts: int = Field(default=5, ge=1, le=100)
    dead_letter_stream: str = "stream:seismik:dead-letter"
    alert_cooldown_seconds: int = Field(default=60, ge=1)
    event_zone_ttl_seconds: int = Field(default=86_400, ge=600)
    push_idempotency_seconds: int = Field(default=86_400, ge=600)
    geofence_radius_km: float = Field(default=250.0, gt=0, le=2_000)
    push_batch_size: int = Field(default=500, ge=1, le=500)
    apns_concurrency: int = Field(default=100, ge=1, le=1_000)
    fcm_concurrency: int = Field(default=20, ge=1, le=200)

    push_enabled: bool = False
    apns_key_path: str | None = None
    apns_key_id: str | None = None
    apns_team_id: str | None = None
    apns_topic: str | None = None
    apns_use_sandbox: bool = False
    firebase_credentials_path: str | None = None
    integrity_verification_enabled: bool = False
    allowed_ios_app_ids: tuple[str, ...] = ()
    allowed_android_app_ids: tuple[str, ...] = ()
    station_catalog_path: str = "config.global.json"
    public_recent_event_limit: int = Field(default=50, ge=1, le=200)

    crowd_pga_threshold_g: float = Field(default=0.04, gt=0, le=5)
    crowd_min_devices: int = Field(default=10, ge=2)
    crowd_window_seconds: float = Field(default=2.5, gt=0, le=10)
    crowd_max_clock_skew_seconds: float = Field(default=5.0, gt=0, le=60)
    crowd_h3_resolution: int = Field(default=7, ge=0, le=15)
    crowd_trigger_cooldown_seconds: int = Field(default=60, ge=1)
    crowd_rate_limit_per_second: int = Field(default=5, ge=1, le=100)
    report_rate_limit_per_minute: int = Field(default=10, ge=1, le=100)

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "AppSettings":
        if self.environment.lower() == "production":
            secrets = {
                self.webhook_hmac_secret.get_secret_value(),
                self.device_api_key.get_secret_value(),
                self.crowd_master_secret.get_secret_value(),
            }
            if any(value.startswith("change-me") for value in secrets):
                raise ValueError("Production requires non-default HMAC/API secrets")
            if not self.integrity_verification_enabled:
                raise ValueError("Production requires App Check integrity verification")
        return self


@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()
