from __future__ import annotations

import asyncio
from dataclasses import dataclass
import hashlib
from typing import Any

import firebase_admin  # type: ignore[import-untyped]
from firebase_admin import app_check, credentials
from fastapi import HTTPException, status

from api.config import AppSettings
from api.schemas import DeviceRegistration, Platform


@dataclass(frozen=True)
class IntegrityVerdict:
    verified: bool
    app_id: str | None
    token_fingerprint: str
    expires_at: int | None


class DeviceIntegrityVerifier:
    """Verifies Firebase App Check tokens minted by platform attestation.

    The mobile fields retain the product-facing App Attest/Play Integrity names,
    but carry short-lived App Check tokens. Raw platform assertions must never be
    accepted or decoded by this API.
    """

    def __init__(self, settings: AppSettings):
        self.settings = settings
        self.firebase_app = self._build_firebase() if settings.integrity_verification_enabled else None

    async def verify(self, registration: DeviceRegistration) -> IntegrityVerdict:
        token = (
            registration.app_attest_token
            if registration.platform is Platform.IOS
            else registration.play_integrity_token
        )
        if token is None:  # Enforced by Pydantic, kept as defense in depth.
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Missing integrity token")
        if self.firebase_app is None:
            return IntegrityVerdict(
                verified=False,
                app_id=None,
                token_fingerprint=hashlib.sha256(token.encode()).hexdigest(),
                expires_at=None,
            )
        try:
            claims: dict[str, Any] = await asyncio.to_thread(
                app_check.verify_token, token, self.firebase_app
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Device integrity verification failed",
            ) from exc

        app_id = str(claims.get("sub") or claims.get("app_id") or "") or None
        allowed = (
            self.settings.allowed_ios_app_ids
            if registration.platform is Platform.IOS
            else self.settings.allowed_android_app_ids
        )
        if allowed and app_id not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Attested application is not allowed",
            )
        expires_at = claims.get("exp")
        return IntegrityVerdict(
            verified=True,
            app_id=app_id,
            token_fingerprint=hashlib.sha256(token.encode()).hexdigest(),
            expires_at=int(expires_at) if isinstance(expires_at, (int, float)) else None,
        )

    def _build_firebase(self) -> firebase_admin.App:
        try:
            return firebase_admin.get_app("seismik-integrity")
        except ValueError:
            credential = (
                credentials.Certificate(self.settings.firebase_credentials_path)
                if self.settings.firebase_credentials_path
                else credentials.ApplicationDefault()
            )
            return firebase_admin.initialize_app(credential, name="seismik-integrity")
