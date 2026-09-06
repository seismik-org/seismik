from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, model_validator

Latitude = Annotated[float, Field(ge=-90, le=90)]
Longitude = Annotated[float, Field(ge=-180, le=180)]


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        json_schema_extra={"x-product": "Seismik"},
    )


class StationTrigger(StrictModel):
    provider_id: str
    country_code: str = Field(min_length=2, max_length=2)
    zone_id: str
    station_id: str
    stream_id: str
    trigger_time: AwareDatetime
    received_at: AwareDatetime
    sta_lta_ratio: float = Field(gt=0)
    peak_amplitude_counts: float | None = Field(default=None, gt=0)
    noise_rms_counts: float | None = Field(default=None, gt=0)
    latitude: Latitude | None = None
    longitude: Longitude | None = None
    packet_lag_seconds: float | None = Field(default=None, ge=0)


class EarthquakeCandidate(StrictModel):
    event_id: str = Field(min_length=1, max_length=128)
    type: Literal["earthquake_candidate"]
    status: Literal["unlocated_unreviewed"]
    zone_id: str = Field(min_length=1, max_length=128)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    country_codes: tuple[str, ...] = Field(min_length=1)
    detected_at: AwareDatetime
    coincidence_window_seconds: float = Field(gt=0)
    required_stations: int = Field(ge=2)
    station_count: int = Field(ge=2)
    stations: tuple[StationTrigger, ...] = Field(min_length=2)
    estimated_latitude: Latitude | None = None
    estimated_longitude: Longitude | None = None
    wave_strength_index: float | None = Field(default=None, ge=0)
    # Solo puede poblarse tras una calibración instrumental validada. La API
    # conserva el campo para permitir esa evolución sin inventar una magnitud.
    magnitude_estimate: float | None = Field(default=None, ge=-2, le=12)
    magnitude_estimate_status: str = Field(
        default="pending_station_calibration", min_length=1, max_length=128
    )

    @model_validator(mode="after")
    def validate_counts(self) -> "EarthquakeCandidate":
        if self.station_count != len(self.stations):
            raise ValueError("station_count must match stations length")
        if self.station_count < self.required_stations:
            raise ValueError("station_count must be >= required_stations")
        station_ids = [station.station_id for station in self.stations]
        if len(set(station_ids)) != len(station_ids):
            raise ValueError("stations must be unique by station_id")
        if any(station.zone_id != self.zone_id for station in self.stations):
            raise ValueError("all stations must belong to candidate zone_id")
        if len(set(self.country_codes)) != len(self.country_codes):
            raise ValueError("country_codes must be unique")
        if any(len(code) != 2 or code.upper() != code for code in self.country_codes):
            raise ValueError("country_codes must contain uppercase ISO alpha-2 codes")
        if self.country_code and self.country_code not in self.country_codes:
            raise ValueError("country_code must be included in country_codes")
        if (self.estimated_latitude is None) != (self.estimated_longitude is None):
            raise ValueError("estimated coordinates must be provided together")
        return self


class OfficialReport(StrictModel):
    source_id: str
    agency: str
    jurisdiction: str
    official_event_id: str
    origin_time: AwareDatetime
    updated_at: AwareDatetime | None = None
    latitude: Latitude
    longitude: Longitude
    depth_km: float | None = Field(default=None, ge=0, le=800)
    magnitude: float | None = Field(default=None, ge=-2, le=12)
    magnitude_type: str | None = None
    place: str | None = None
    review_status: str | None = None
    official_url: HttpUrl
    attribution: str | None = None
    tsunami: bool | None = None
    felt: str | None = None
    distance_from_station_centroid_km: float | None = Field(default=None, ge=0)
    origin_time_delta_seconds: float | None = Field(default=None, ge=0)


class OfficialReportUpdate(StrictModel):
    event_id: str = Field(min_length=1, max_length=128)
    candidate_event_id: str = Field(min_length=1, max_length=128)
    type: Literal["official_report_update"]
    status: Literal["official_report_available"]
    matched_at: AwareDatetime
    preferred_report: OfficialReport
    reports: tuple[OfficialReport, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_preferred_report(self) -> "OfficialReportUpdate":
        identities = [(item.source_id, item.official_event_id) for item in self.reports]
        preferred = (
            self.preferred_report.source_id,
            self.preferred_report.official_event_id,
        )
        if preferred not in identities:
            raise ValueError("preferred_report must be included in reports")
        if len(set(identities)) != len(identities):
            raise ValueError("reports must be unique by source and official_event_id")
        return self


class Platform(StrEnum):
    IOS = "ios"
    ANDROID = "android"


class DeviceRegistration(StrictModel):
    device_id: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    platform: Platform
    apns_token: str | None = Field(default=None, min_length=32, max_length=512)
    fcm_token: str | None = Field(default=None, min_length=32, max_length=4096)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    zone_id: str | None = Field(default=None, min_length=1, max_length=128)
    latitude: Latitude | None = None
    longitude: Longitude | None = None
    critical_alerts_authorized: bool = False
    receive_early_alerts: bool = True
    receive_official_updates: bool = True
    minimum_notification_magnitude: float = Field(default=4.0, ge=0, le=10)
    alert_radius_km: float = Field(
        default=250.0,
        ge=10,
        le=2_000,
        description="Radio máximo, elegido por la persona, para recibir avisos",
    )
    locale: str = Field(default="es", min_length=2, max_length=16)
    app_attest_token: str | None = Field(
        default=None,
        min_length=16,
        max_length=8192,
        description="Firebase App Check token backed by App Attest/DeviceCheck",
    )
    play_integrity_token: str | None = Field(
        default=None,
        min_length=16,
        max_length=8192,
        description="Firebase App Check token backed by Play Integrity",
    )

    @model_validator(mode="after")
    def validate_platform_and_location(self) -> "DeviceRegistration":
        if self.platform is Platform.IOS and not self.apns_token:
            raise ValueError("ios requires apns_token")
        if self.platform is Platform.ANDROID and not self.fcm_token:
            raise ValueError("android requires fcm_token")
        if self.platform is Platform.IOS and self.fcm_token:
            raise ValueError("ios cannot register fcm_token")
        if self.platform is Platform.ANDROID and self.apns_token:
            raise ValueError("android cannot register apns_token")
        if self.platform is Platform.IOS and not self.app_attest_token:
            raise ValueError("ios requires app_attest_token")
        if self.platform is Platform.ANDROID and not self.play_integrity_token:
            raise ValueError("android requires play_integrity_token")
        if self.platform is Platform.IOS and self.play_integrity_token:
            raise ValueError("ios cannot register play_integrity_token")
        if self.platform is Platform.ANDROID and self.app_attest_token:
            raise ValueError("android cannot register app_attest_token")
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be provided together")
        if not self.zone_id and self.latitude is None:
            raise ValueError("zone_id or coordinates are required")
        return self

    @property
    def token(self) -> str:
        return self.apns_token or self.fcm_token or ""


class DeviceRegistrationResponse(StrictModel):
    device_id: str
    registered: bool
    crowd_token: str
    device_session_token: str


class DeviceUnregister(StrictModel):
    device_id: str = Field(min_length=8, max_length=128)


class AcceptedResponse(StrictModel):
    accepted: bool = True
    duplicate: bool = False
    stream_id: str | None = None


class DeviceTarget(StrictModel):
    device_id: str
    platform: Platform
    token: str
    critical_alerts_authorized: bool = False
    receive_early_alerts: bool = True
    receive_official_updates: bool = True
    minimum_notification_magnitude: float = 4.0
    alert_radius_km: float = 250.0
    latitude: Latitude | None = None
    longitude: Longitude | None = None
    locale: str = "es"


class AlertLedgerEntry(StrictModel):
    """Alerta ya emitida, recuperable por una app que estuvo sin conexión."""

    event_id: str
    type: str
    critical: bool
    emitted_at: AwareDatetime
    zone_id: str | None = None
    latitude: Latitude | None = None
    longitude: Longitude | None = None
    magnitude: float | None = None
    depth_km: float | None = None
    place: str | None = None
    agency: str | None = None
    official_url: str | None = None


class AlertLedgerPage(StrictModel):
    alerts: tuple[AlertLedgerEntry, ...] = ()
    cursor: str | None = None


class ShakePing(StrictModel):
    device_id: str = Field(min_length=8, max_length=128)
    lat: Latitude
    lon: Longitude
    pga: float = Field(ge=0, le=5, description="Peak ground acceleration in g")
    timestamp: float = Field(
        gt=0,
        description="Unix timestamp; milliseconds preferred, seconds accepted for compatibility",
    )

    @property
    def timestamp_seconds(self) -> float:
        return self.timestamp / 1000 if self.timestamp >= 100_000_000_000 else self.timestamp


class ShakeAccepted(StrictModel):
    accepted: bool = True
    above_threshold: bool
    cell_id: str | None = None
    independent_devices: int = 0
    triggered: bool = False


class CrowdsourcedCandidate(StrictModel):
    event_id: str
    type: Literal["crowdsourced_earthquake_candidate"]
    status: Literal["unlocated_unreviewed"]
    zone_id: str
    detected_at: AwareDatetime
    estimated_latitude: Latitude
    estimated_longitude: Longitude
    pga_threshold_g: float
    device_count: int
    window_seconds: float
    source: Literal["mobile_accelerometer_h3_cluster"] = (
        "mobile_accelerometer_h3_cluster"
    )
