from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from api.schemas import Latitude, Longitude, StrictModel


class LocationPrecision(StrEnum):
    APPROXIMATE = "approximate"
    PRECISE = "precise"


class DamageSeverity(StrEnum):
    NONE = "none"
    MINOR = "minor"
    MODERATE = "moderate"
    SEVERE = "severe"
    COLLAPSE = "collapse"


class ObservedHazard(StrEnum):
    FIRE = "fire"
    GAS_LEAK = "gas_leak"
    ELECTRICAL = "electrical"
    WATER_LEAK = "water_leak"
    LANDSLIDE = "landslide"
    ROAD_BLOCKED = "road_blocked"
    STRUCTURAL_INSTABILITY = "structural_instability"


class CitizenReportBase(StrictModel):
    report_id: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    device_id: str = Field(min_length=8, max_length=128)
    earthquake_event_id: str | None = Field(default=None, min_length=1, max_length=128)
    official_event_id: str | None = Field(default=None, min_length=1, max_length=128)
    observed_at: datetime
    latitude: Latitude
    longitude: Longitude
    location_accuracy_m: float | None = Field(default=None, ge=0, le=100_000)
    location_precision: LocationPrecision = LocationPrecision.APPROXIMATE
    country_code: str = Field(min_length=2, max_length=2)
    share_with_official_agencies: bool = False
    consent_version: Literal["2026-08"] = "2026-08"
    comment: str | None = Field(default=None, max_length=1_000)


class FeltReport(CitizenReportBase):
    type: Literal["seismik_felt_report"] = "seismik_felt_report"
    felt: bool
    intensity_mmi: int | None = Field(default=None, ge=1, le=10)
    indoors: bool | None = None
    floor: int | None = Field(default=None, ge=-5, le=200)
    woke_up: bool | None = None
    difficulty_standing: bool | None = None
    objects_moved: bool | None = None
    objects_fell: bool | None = None
    visible_damage: bool | None = None

    @model_validator(mode="after")
    def validate_intensity(self) -> "FeltReport":
        if self.felt and self.intensity_mmi is None:
            raise ValueError("intensity_mmi is required when felt=true")
        if not self.felt and self.intensity_mmi is not None:
            raise ValueError("intensity_mmi must be omitted when felt=false")
        return self


class DamageReport(CitizenReportBase):
    type: Literal["seismik_damage_report"] = "seismik_damage_report"
    severity: DamageSeverity
    hazards: tuple[ObservedHazard, ...] = ()
    building_type: str | None = Field(default=None, max_length=80)
    people_trapped: bool = False
    injuries_observed: bool = False
    emergency_services_contacted: bool = False
    safe_to_remain: bool | None = None

    @property
    def requires_emergency_action(self) -> bool:
        return (
            self.people_trapped
            or self.injuries_observed
            or self.severity in {DamageSeverity.SEVERE, DamageSeverity.COLLAPSE}
            or any(
                hazard in {ObservedHazard.FIRE, ObservedHazard.GAS_LEAK}
                for hazard in self.hazards
            )
        )


class AgencyRoute(StrictModel):
    agency_id: str
    agency_name: str
    country_code: str | None = None
    report_kind: Literal["felt_and_effects"] = "felt_and_effects"
    submission_mode: Literal["external_form"] = "external_form"
    official_url: str
    automatic_submission: bool = False


class ReportAccepted(StrictModel):
    accepted: bool
    duplicate: bool = False
    stream_id: str | None = None
    report_id: str
    stored_location_precision: LocationPrecision
    emergency_action_recommended: bool = False
    agency_routes: tuple[AgencyRoute, ...] = ()
    notice: str
