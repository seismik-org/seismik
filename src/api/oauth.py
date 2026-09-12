from __future__ import annotations

import base64
import hashlib
import json
import secrets
from urllib.parse import urlencode, urlparse

import httpx
from fastapi import APIRouter, Body, Cookie, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse

router = APIRouter(prefix="/v1/oauth", tags=["oauth"])
identity_router = APIRouter(tags=["oauth"])

_MOBILE_CALLBACK = "seismik://auth/callback"
_MOBILE_CODE_TTL_SECONDS = 60
_IDENTITY_FLOW_TTL_SECONDS = 600


def _pkce_verifier() -> str:
    return secrets.token_urlsafe(48)


def _challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def _cookie_name() -> str:
    return "seismik_session"


def _mobile_return_to(value: str | None) -> str | None:
    """Accept exactly the app callback; never turn OAuth into an open redirect."""
    if value is None:
        return None
    parsed = urlparse(value)
    if (
        parsed.scheme == "seismik"
        and parsed.netloc == "auth"
        and parsed.path == "/callback"
        and not parsed.params
        and not parsed.query
        and not parsed.fragment
    ):
        return _MOBILE_CALLBACK
    raise HTTPException(status_code=400, detail="Callback móvil OAuth no permitido")


async def _finish_login(
    request: Request,
    user: dict[str, str],
    return_to: str | None,
) -> Response:
    """Issue the browser cookie and, only for the native app, a one-time code."""
    settings = request.app.state.settings
    session = secrets.token_urlsafe(48)
    await request.app.state.redis.set(
        f"seismik:oauth:session:{session}",
        json.dumps(user),
        ex=settings.oauth_session_ttl_seconds,
    )
    target = settings.developer_portal_url
    if return_to:
        code = secrets.token_urlsafe(32)
        await request.app.state.redis.set(
            f"seismik:oauth:mobile-code:{code}",
            json.dumps(user),
            ex=_MOBILE_CODE_TTL_SECONDS,
        )
        target = return_to + "?" + urlencode({"code": code})
    response = RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        _cookie_name(), session, max_age=settings.oauth_session_ttl_seconds,
        secure=True, httponly=True, samesite="lax", path="/",
        domain=settings.oauth_cookie_domain,
    )
    return response


def _github_is_configured(settings: object) -> bool:
    return bool(
        getattr(settings, "oauth_github_client_id", "")
        and getattr(settings, "oauth_github_client_secret").get_secret_value()
    )


@router.get("/providers")
async def oauth_providers(request: Request) -> dict[str, dict[str, dict[str, bool]]]:
    """Expone sólo disponibilidad; no IDs de cliente ni secretos."""
    settings = request.app.state.settings
    return {
        "providers": {
            "google": {
                "enabled": bool(
                    settings.oauth_google_client_id
                    and settings.oauth_google_client_secret.get_secret_value()
                )
            },
            "github": {"enabled": _github_is_configured(settings)},
        }
    }


@router.get("/login")
async def login(
    request: Request, provider: str = "google", return_to: str | None = None
) -> Response:
    """Entrada estable de auth.seismik.org para el portal de desarrolladores."""
    if provider == "google":
        return await google_start(request, return_to=return_to)
    if provider == "github":
        return await github_start(request, return_to=return_to)
    raise HTTPException(status_code=404, detail="Proveedor OAuth no disponible")


@router.get("/authorize")
async def authorize(request: Request, provider: str = "google", origin: str = "devs") -> Response:
    """Crea un identificador opaco para el inicio de sesión.

    El navegador sólo ve ``auth.seismik.org/id/<aleatorio>`` antes de ir al
    proveedor. El origen permitido decide el retorno: el portal de
    desarrolladores o el esquema de la app; no se acepta una URL arbitraria.
    """
    if provider not in {"google", "github"}:
        raise HTTPException(status_code=404, detail="Proveedor OAuth no disponible")
    returns = {"devs": None, "app": _MOBILE_CALLBACK}
    if origin not in returns:
        raise HTTPException(status_code=400, detail="Origen OAuth no permitido")
    flow_id = secrets.token_urlsafe(24)
    await request.app.state.redis.set(
        f"seismik:oauth:identity:{flow_id}",
        json.dumps({"provider": provider, "return_to": returns[origin], "origin": origin}),
        ex=_IDENTITY_FLOW_TTL_SECONDS,
    )
    return RedirectResponse(f"/id/{flow_id}", status_code=status.HTTP_303_SEE_OTHER)


@identity_router.get("/id/{flow_id}")
async def identity_entry(request: Request, flow_id: str) -> Response:
    """Consume la intención guardada y arranca el proveedor correspondiente."""
    if len(flow_id) < 24 or len(flow_id) > 128:
        raise HTTPException(status_code=404, detail="Solicitud de inicio de sesión inválida")
    raw = await request.app.state.redis.get(f"seismik:oauth:identity:{flow_id}")
    if not raw:
        raise HTTPException(status_code=410, detail="Esta solicitud de inicio de sesión expiró")
    saved = json.loads(raw)
    if saved.get("provider") == "google":
        return await google_start(request, return_to=saved.get("return_to"))
    if saved.get("provider") == "github":
        return await github_start(request, return_to=saved.get("return_to"))
    raise HTTPException(status_code=400, detail="Solicitud de inicio de sesión inválida")


@router.get("/google/start")
async def google_start(request: Request, return_to: str | None = None) -> Response:
    settings = request.app.state.settings
    if not settings.oauth_google_client_id or not settings.oauth_google_client_secret.get_secret_value():
        raise HTTPException(status_code=503, detail="OAuth directo no está configurado")
    state = secrets.token_urlsafe(32)
    verifier = _pkce_verifier()
    await request.app.state.redis.set(
        f"seismik:oauth:state:{state}",
        json.dumps({"verifier": verifier, "return_to": _mobile_return_to(return_to)}),
        ex=600,
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
    saved = json.loads(raw)
    verifier = saved["verifier"]
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
    return await _finish_login(
        request,
        {"uid": user.get("sub", ""), "email": user["email"], "name": user.get("name", "")},
        saved.get("return_to"),
    )


@router.get("/github/start")
async def github_start(request: Request, return_to: str | None = None) -> Response:
    settings = request.app.state.settings
    if not _github_is_configured(settings):
        raise HTTPException(status_code=503, detail="GitHub OAuth aún no está configurado")
    state = secrets.token_urlsafe(32)
    verifier = _pkce_verifier()
    await request.app.state.redis.set(
        f"seismik:oauth:state:{state}",
        json.dumps(
            {"provider": "github", "verifier": verifier, "return_to": _mobile_return_to(return_to)}
        ),
        ex=600,
    )
    params = {
        "client_id": settings.oauth_github_client_id,
        "redirect_uri": settings.oauth_github_redirect_uri,
        "response_type": "code",
        "scope": "read:user user:email",
        "state": state,
        "code_challenge": _challenge(verifier),
        "code_challenge_method": "S256",
    }
    return RedirectResponse("https://github.com/login/oauth/authorize?" + urlencode(params))


@router.get("/github/callback")
async def github_callback(
    request: Request, code: str | None = None, state: str | None = None
) -> Response:
    settings = request.app.state.settings
    if not code or not state:
        raise HTTPException(status_code=400, detail="Respuesta OAuth incompleta")
    raw = await request.app.state.redis.get(f"seismik:oauth:state:{state}")
    if not raw:
        raise HTTPException(status_code=400, detail="Estado OAuth inválido o expirado")
    await request.app.state.redis.delete(f"seismik:oauth:state:{state}")
    saved = json.loads(raw)
    if saved.get("provider") != "github":
        raise HTTPException(status_code=400, detail="Estado OAuth no coincide con GitHub")
    async with httpx.AsyncClient(timeout=10) as client:
        token_response = await client.post(
            "https://github.com/login/oauth/access_token",
            data={
                "client_id": settings.oauth_github_client_id,
                "client_secret": settings.oauth_github_client_secret.get_secret_value(),
                "code": code,
                "code_verifier": saved["verifier"],
                "grant_type": "authorization_code",
                "redirect_uri": settings.oauth_github_redirect_uri,
            },
            headers={"Accept": "application/json"},
        )
        if token_response.is_error or not token_response.json().get("access_token"):
            raise HTTPException(status_code=401, detail="GitHub no pudo validar el código OAuth")
        headers = {
            "Authorization": f"Bearer {token_response.json()['access_token']}",
            "Accept": "application/json",
        }
        profile = await client.get("https://api.github.com/user", headers=headers)
        emails = await client.get("https://api.github.com/user/emails", headers=headers)
    if profile.is_error or emails.is_error:
        raise HTTPException(status_code=401, detail="No se pudo obtener el perfil GitHub")
    email_record = next(
        (
            item
            for item in emails.json()
            if item.get("primary") and item.get("verified") and item.get("email")
        ),
        None,
    )
    if not email_record:
        raise HTTPException(status_code=403, detail="GitHub requiere un correo primario verificado")
    github_user = profile.json()
    return await _finish_login(
        request,
        {
            "uid": f"github:{github_user.get('id', '')}",
            "email": email_record["email"],
            "name": github_user.get("name") or github_user.get("login", ""),
        },
        saved.get("return_to"),
    )


@router.post("/mobile/exchange")
async def exchange_mobile_code(request: Request, code: str = Body(embed=True, min_length=20)) -> dict[str, str]:
    """Exchange a single-use app callback code for a Keychain-held session."""
    raw = await request.app.state.redis.getdel(f"seismik:oauth:mobile-code:{code}")
    if not raw:
        raise HTTPException(status_code=401, detail="Código móvil OAuth inválido o expirado")
    settings = request.app.state.settings
    token = secrets.token_urlsafe(48)
    await request.app.state.redis.set(
        f"seismik:oauth:mobile-session:{token}", raw, ex=settings.oauth_session_ttl_seconds
    )
    user = json.loads(raw)
    return {"mobile_session_token": token, "uid": user["uid"], "email": user["email"], "name": user["name"]}


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
    response.delete_cookie(
        _cookie_name(), path="/", domain=request.app.state.settings.oauth_cookie_domain
    )
