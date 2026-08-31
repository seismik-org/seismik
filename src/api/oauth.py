from __future__ import annotations

import base64
import hashlib
import json
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Cookie, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse

router = APIRouter(prefix="/v1/oauth", tags=["oauth"])


def _pkce_verifier() -> str:
    return secrets.token_urlsafe(48)


def _challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def _cookie_name() -> str:
    return "seismik_session"


@router.get("/google/start")
async def google_start(request: Request) -> Response:
    settings = request.app.state.settings
    if not settings.oauth_google_client_id or not settings.oauth_google_client_secret.get_secret_value():
        raise HTTPException(status_code=503, detail="OAuth directo no está configurado")
    state = secrets.token_urlsafe(32)
    verifier = _pkce_verifier()
    await request.app.state.redis.setex(
        f"seismik:oauth:state:{state}",
        600,
        json.dumps({"verifier": verifier}),
    )
    params = {
        "client_id": settings.oauth_google_client_id,
        "redirect_uri": settings.oauth_google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "code_challenge": _challenge(verifier),
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "select_account",
    }
    return RedirectResponse("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params))


@router.get("/google/callback")
async def google_callback(request: Request, code: str | None = None, state: str | None = None) -> Response:
    settings = request.app.state.settings
    if not code or not state:
        raise HTTPException(status_code=400, detail="Respuesta OAuth incompleta")
    raw = await request.app.state.redis.get(f"seismik:oauth:state:{state}")
    if not raw:
        raise HTTPException(status_code=400, detail="Estado OAuth inválido o expirado")
    await request.app.state.redis.delete(f"seismik:oauth:state:{state}")
    verifier = json.loads(raw)["verifier"]
    async with httpx.AsyncClient(timeout=10) as client:
        token_response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": settings.oauth_google_client_id,
                "client_secret": settings.oauth_google_client_secret.get_secret_value(),
                "code": code,
                "code_verifier": verifier,
                "grant_type": "authorization_code",
                "redirect_uri": settings.oauth_google_redirect_uri,
            },
        )
        if token_response.is_error:
            raise HTTPException(status_code=401, detail="Google no pudo validar el código OAuth")
        token = token_response.json()
        profile = await client.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {token['access_token']}"},
        )
    if profile.is_error:
        raise HTTPException(status_code=401, detail="No se pudo obtener el perfil Google")
    user = profile.json()
    if not user.get("email_verified", False):
        raise HTTPException(status_code=403, detail="Se requiere un correo Google verificado")
    session = secrets.token_urlsafe(48)
    await request.app.state.redis.setex(
        f"seismik:oauth:session:{session}",
        settings.oauth_session_ttl_seconds,
        json.dumps({"uid": user.get("sub", ""), "email": user["email"], "name": user.get("name", "")}),
    )
    response = RedirectResponse("https://devs.seismik.org/", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        _cookie_name(), session, max_age=settings.oauth_session_ttl_seconds,
        secure=True, httponly=True, samesite="lax", path="/",
    )
    return response


@router.get("/session")
async def current_session(request: Request, seismik_session: str | None = Cookie(default=None)) -> dict[str, str]:
    if not seismik_session:
        raise HTTPException(status_code=401, detail="Sesión requerida")
    raw = await request.app.state.redis.get(f"seismik:oauth:session:{seismik_session}")
    if not raw:
        raise HTTPException(status_code=401, detail="Sesión expirada")
    return json.loads(raw)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, seismik_session: str | None = Cookie(default=None)) -> None:
    if seismik_session:
        await request.app.state.redis.delete(f"seismik:oauth:session:{seismik_session}")
    response.delete_cookie(_cookie_name(), path="/")
