from __future__ import annotations

import pytest
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
