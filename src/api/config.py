from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
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
    event_max_body_bytes: int = Field(default=65_536, ge=1_024, le=1_048_576)
    consumer_api_key: SecretStr = SecretStr("")
    # Secreto compartido con el Worker de Cloudflare y el reenviador de
    # Pub/Sub. Vacío, la API atiende a cualquiera; definido, rechaza lo que
    # llegue a su URL de Cloud Run sin él. Ver api/edge_origin.py.
    edge_origin_secret: SecretStr = SecretStr("")
    device_session_ttl_seconds: int = Field(default=2_592_000, ge=3_600, le=31_536_000)
    crowd_master_secret: SecretStr = SecretStr("change-me-crowd-secret")
    developer_portal_origins: tuple[str, ...] = ("https://devs.seismik.org",)
    developer_portal_url: str = "https://devs.seismik.org/"
    developer_terms_version: str = "2026-08-30"
    developer_max_active_keys: int = Field(default=3, ge=1, le=20)
    developer_free_requests_per_minute: int = Field(default=60, ge=1, le=10_000)
    developer_free_requests_per_day: int = Field(default=10_000, ge=10, le=10_000_000)
    # Acota el bucle de crear y revocar: el máximo de claves activas no lo
    # frena, porque revocar libera un hueco de inmediato.
    developer_key_creations_per_hour: int = Field(default=10, ge=1, le=1_000)
    developer_audit_stream: str = "stream:seismik:developer-audit"
    integration_stream: str = "stream:seismik:integrations"
    integration_dead_letter_stream: str = "stream:seismik:integrations-dead-letter"
    integration_audit_stream: str = "stream:seismik:integration-audit"
    integration_dispatcher_group: str = "integration-dispatchers"
    integration_consumer_name: str = "integration-dispatcher-1"
    integration_delivery_timeout_seconds: float = Field(default=5.0, ge=1, le=20)
    integration_delivery_max_attempts: int = Field(default=5, ge=1, le=20)
    integration_delivery_concurrency: int = Field(default=20, ge=1, le=100)
    integration_webhook_master_secret: SecretStr = SecretStr("change-me-integration-secret")
    x_publisher_enabled: bool = False
    x_publisher_dry_run: bool = True
    x_publisher_minimum_magnitude: float = Field(default=2.5, ge=0, le=10)
    # Adjunta la imagen del boletín (integrations/bulletin_card.py) a cada post.
    x_publisher_images: bool = True
    # Qué publica: los sismos nuevos de los catálogos de official_sources.json o
    # las actualizaciones oficiales de las detecciones propias por SeedLink.
    x_publisher_source: Literal["official_catalogs", "seismik_detections"] = "official_catalogs"
    x_publisher_poll_seconds: float = Field(default=120.0, ge=30, le=3_600)
    x_publisher_max_age_minutes: float = Field(default=60.0, ge=5, le=1_440)
    # Dos reportes son el mismo sismo si sus orígenes y epicentros están así de cerca.
    x_publisher_duplicate_seconds: float = Field(default=90.0, ge=10, le=900)
    x_publisher_duplicate_km: float = Field(default=150.0, ge=10, le=1_000)
    # Dentro de los países de una agencia local, el USGS espera a que ésta publique.
    x_publisher_global_settle_minutes: float = Field(default=15.0, ge=0, le=120)
    x_publisher_stream: str = "stream:seismik:x-publisher"
    x_publisher_group: str = "x-publishers"
    x_publisher_consumer_name: str = "x-publisher-1"
    x_consumer_key: SecretStr = SecretStr("")
    x_consumer_secret: SecretStr = SecretStr("")
    x_access_token: SecretStr = SecretStr("")
    x_access_token_secret: SecretStr = SecretStr("")
    firebase_web_api_key: str = ""
    firebase_web_auth_domain: str = ""
    firebase_web_project_id: str = ""
    firebase_web_app_id: str = ""
    oauth_google_client_id: str = ""
    oauth_google_client_secret: SecretStr = SecretStr("")
    # auth.seismik.org es el único origen del flujo de identidad. Así los
    # proveedores no necesitan conocer las páginas privadas del portal.
    oauth_google_redirect_uri: str = "https://auth.seismik.org/v1/oauth/google/callback"
    oauth_github_client_id: str = ""
    oauth_github_client_secret: SecretStr = SecretStr("")
    oauth_github_redirect_uri: str = "https://auth.seismik.org/v1/oauth/github/callback"
    oauth_cookie_domain: str = ".seismik.org"
    oauth_session_ttl_seconds: int = Field(default=86_400, ge=300, le=2_592_000)
    # Sesión de la cuenta en la app: dura más que la del navegador y se renueva
    # con el uso. Búsqueda de familiares no puede pedir iniciar sesión justo
    # después de un sismo porque la sesión venció la noche anterior.
    mobile_account_session_ttl_seconds: int = Field(
        default=7_776_000, ge=3_600, le=31_536_000
    )

    candidate_stream: str = "stream:seismik:candidates"
    official_stream: str = "stream:seismik:official"
    felt_reports_stream: str = "stream:seismik:felt-reports"
    damage_reports_stream: str = "stream:seismik:damage-reports"
    family_notification_stream: str = "stream:seismik:family-notifications"
    # Un «estoy bien» vale para los días siguientes al sismo, no para siempre.
    family_status_ttl_seconds: int = Field(default=259_200, ge=3_600, le=2_592_000)
    stream_maxlen: int = Field(default=100_000, ge=1_000)
    dispatcher_group: str = "push-dispatchers"
    consumer_name: str = "dispatcher-1"
    consumer_block_ms: int = Field(default=1_000, ge=10, le=60_000)
    consumer_batch_size: int = Field(default=10, ge=1, le=1_000)
    pending_claim_idle_ms: int = Field(default=30_000, ge=1_000)
    max_delivery_attempts: int = Field(default=5, ge=1, le=100)
    dead_letter_stream: str = "stream:seismik:dead-letter"
    alert_cooldown_seconds: int = Field(default=60, ge=1)
    # Ventana en la que un mismo event_id no vuelve a generar una alerta,
    # incluso si el stream lo reentrega tras un reinicio del dispatcher.
    alert_dedup_seconds: int = Field(default=1_800, ge=60)
    # Bitácora consultable por la app para recuperar alertas perdidas offline.
    alert_ledger_stream: str = "stream:seismik:alert-ledger"
    alert_ledger_maxlen: int = Field(default=10_000, ge=100)
    alert_recent_limit: int = Field(default=50, ge=1, le=200)
    event_zone_ttl_seconds: int = Field(default=86_400, ge=600)
    push_idempotency_seconds: int = Field(default=86_400, ge=600)
    geofence_radius_km: float = Field(default=250.0, gt=0, le=2_000)
    push_batch_size: int = Field(default=500, ge=1, le=500)
    apns_concurrency: int = Field(default=100, ge=1, le=1_000)
    fcm_concurrency: int = Field(default=20, ge=1, le=200)

    push_enabled: bool = False
    push_mode: Literal["dry_run", "testers", "production"] = "dry_run"
    push_test_device_ids: tuple[str, ...] = ()
    push_audit_stream: str = "stream:seismik:push-test"
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
    official_sources_path: str = "official_sources.json"
    official_history_timeout_seconds: float = Field(default=8.0, ge=1, le=30)
    official_history_cache_seconds: int = Field(default=120, ge=30, le=3_600)

    crowd_pga_threshold_g: float = Field(default=0.04, gt=0, le=5)
    crowd_min_devices: int = Field(default=10, ge=2)
    crowd_window_seconds: float = Field(default=2.5, gt=0, le=10)
    crowd_max_clock_skew_seconds: float = Field(default=5.0, gt=0, le=60)
    crowd_h3_resolution: int = Field(default=7, ge=0, le=15)
    crowd_trigger_cooldown_seconds: int = Field(default=60, ge=1)
    crowd_rate_limit_per_second: int = Field(default=5, ge=1, le=100)
    report_rate_limit_per_minute: int = Field(default=10, ge=1, le=100)

    @field_validator("oauth_google_client_id", "oauth_github_client_id", mode="before")
    @classmethod
    def strip_oauth_client_id(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator(
        "oauth_google_client_secret",
        "oauth_github_client_secret",
        "edge_origin_secret",
        mode="before",
    )
    @classmethod
    def strip_secret(cls, value: object) -> object:
        # En el secreto de origen, ese salto de línea haría que la API rechazara
        # con 403 todo lo que llega por el Worker de Cloudflare.
        # Un secreto guardado con `echo` en Secret Manager arrastra un salto de
        # línea final. Google lo rechaza como `invalid_client` y el mensaje no
        # dice por qué: basta un carácter invisible para romper el inicio de sesión.
        if isinstance(value, SecretStr):
            return SecretStr(value.get_secret_value().strip())
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "AppSettings":
        if self.push_enabled and self.push_mode == "dry_run":
            raise ValueError("push_enabled requires push_mode testers or production")
        if not self.push_enabled and self.push_mode != "dry_run":
            raise ValueError("dry_run is required while push delivery is disabled")
        if self.push_mode == "testers" and not self.push_test_device_ids:
            raise ValueError("Tester push requires a non-empty device allowlist")
        if self.push_mode == "production" and self.environment.lower() != "production":
            raise ValueError("Production push requires the production environment")
        if self.environment.lower() == "production":
            # Se valida primero porque una instalación sin atestación nunca es
            # apta para producción, incluso si todos los secretos existen.
            if not self.integrity_verification_enabled:
                raise ValueError("Production requires App Check integrity verification")
        if self.environment.lower() in ("production", "staging"):
            secrets = {
                self.webhook_hmac_secret.get_secret_value(),
                self.crowd_master_secret.get_secret_value(),
                self.integration_webhook_master_secret.get_secret_value(),
            }
            if any(value.startswith("change-me") for value in secrets):
                raise ValueError(
                    f"{self.environment.capitalize()} requires non-default HMAC/API secrets"
                )
            if not self.consumer_api_key.get_secret_value():
                raise ValueError(
                    f"{self.environment.capitalize()} requires a consumer API key"
                )
        return self


@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()
