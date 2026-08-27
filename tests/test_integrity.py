from __future__ import annotations

import pytest
from fastapi import HTTPException
from firebase_admin import app_check
from pydantic import ValidationError

from api.config import AppSettings
from api.integrity import DeviceIntegrityVerifier
from api.schemas import DeviceRegistration


def test_registration_requires_platform_integrity_token() -> None:
    with pytest.raises(ValidationError, match="play_integrity_token"):
        DeviceRegistration(
            device_id="device-0001",
            platform="android",
            fcm_token="f" * 64,
            zone_id="andes",
        )


@pytest.mark.asyncio
async def test_development_verifier_accepts_typed_token_without_remote_call() -> None:
    verifier = DeviceIntegrityVerifier(AppSettings(integrity_verification_enabled=False))
    verdict = await verifier.verify(
        DeviceRegistration(
            device_id="device-0001",
            platform="android",
            fcm_token="f" * 64,
            zone_id="andes",
            play_integrity_token="firebase-app-check-debug-token",
        )
    )
    assert not verdict.verified
    assert len(verdict.token_fingerprint) == 64


def test_production_refuses_disabled_integrity_verification() -> None:
    with pytest.raises(ValidationError, match="App Check"):
        AppSettings(
            environment="production",
            webhook_hmac_secret="production-webhook-secret",
            device_api_key="production-device-key",
            crowd_master_secret="production-crowd-secret",
            integrity_verification_enabled=False,
        )


def test_push_delivery_requires_explicit_tester_allowlist() -> None:
    with pytest.raises(ValidationError, match="allowlist"):
        AppSettings(push_enabled=True, push_mode="testers")

    settings = AppSettings(
        push_enabled=True,
        push_mode="testers",
        push_test_device_ids=("device-0001",),
    )
    assert settings.push_test_device_ids == ("device-0001",)


def test_production_push_cannot_be_enabled_from_development() -> None:
    with pytest.raises(ValidationError, match="production environment"):
        AppSettings(push_enabled=True, push_mode="production")


@pytest.mark.asyncio
async def test_invalid_remote_app_check_token_is_rejected(monkeypatch) -> None:
    verifier = DeviceIntegrityVerifier(AppSettings(integrity_verification_enabled=False))
    verifier.firebase_app = object()  # type: ignore[assignment]

    def reject(_token, _app):
        raise ValueError("invalid test token")

    monkeypatch.setattr(app_check, "verify_token", reject)
    registration = DeviceRegistration(
        device_id="device-0001",
        platform="android",
        fcm_token="f" * 64,
        zone_id="andes",
        play_integrity_token="invalid-app-check-token",
    )
    with pytest.raises(HTTPException) as error:
        await verifier.verify(registration)
    assert error.value.status_code == 401
