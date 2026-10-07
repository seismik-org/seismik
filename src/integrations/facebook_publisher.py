"""Boletines oficiales en Facebook; mismas reglas de catálogo que X.

Las marcas de publicación y auditoría son independientes de X. No se ejecuta
hasta habilitarlo y configurar una credencial de la página en Secret Manager.
"""
from __future__ import annotations

import asyncio
from typing import Any

import requests

from integrations.x_publisher import XPublisher, bulletin_text


class FacebookPublisher(XPublisher):
    namespace = "facebook"

    async def run(self) -> None:
        # Facebook replica los catálogos oficiales, no consume el grupo de X.
        if not self.settings.facebook_publisher_enabled:
            return
        if not self.settings.facebook_publisher_dry_run and (
            not self.settings.facebook_page_id.isdecimal()
            or not self.settings.facebook_page_access_token.get_secret_value()
        ):
            raise ValueError("Falta configurar la página o la credencial de Facebook")
        await self._run_catalogs()

    async def _publish(self, event: dict[str, Any], published_key: str) -> None:
        event_id = str(event["event_id"])
        text = bulletin_text(event)
        image = await self._render_card(event)
        if not self.settings.facebook_publisher_enabled or self.settings.facebook_publisher_dry_run:
            await self._audit(event_id, "dry_run", text=text, image="yes" if image else "no")
            return
        page = self.settings.facebook_page_id
        if not page.isdecimal():
            await self.redis.delete(published_key)
            raise ValueError("Identificador de página inválido")
        token = self.settings.facebook_page_access_token.get_secret_value()
        if not token:
            await self.redis.delete(published_key)
            raise ValueError("Falta la credencial de página")
        base = f"https://graph.facebook.com/{self.settings.facebook_graph_version}/{page}"
        # El token va en cabecera, nunca en URL, Redis ni registros.
        try:
            response = await asyncio.to_thread(
                requests.post,
                f"{base}/photos" if image else f"{base}/feed",
                headers={"Authorization": f"Bearer {token}"},
                data={"message": text},
                files={"source": ("boletin.png", image, "image/png")} if image else None,
                timeout=30,
            )
        except requests.RequestException:
            # Una respuesta perdida puede ocultar un envío correcto. No
            # reintentamos a ciegas un boletín público potencialmente publicado.
            await self.redis.set(published_key, "uncertain", ex=2_592_000)
            await self._audit(event_id, "delivery_uncertain")
            return
        if response.status_code >= 500:
            await self.redis.set(published_key, "uncertain", ex=2_592_000)
            await self._audit(event_id, "delivery_uncertain", status=str(response.status_code))
            return
        if not 200 <= response.status_code < 300:
            await self.redis.delete(published_key)
            # El cuerpo de Meta puede contener datos de credenciales. Sólo
            # guardamos el código HTTP; el catálogo aplica sus reintentos finitos.
            raise RuntimeError(f"Facebook rechazó el envío HTTP {response.status_code}")
        try:
            body = response.json()
            post_id = str(body.get("post_id") or body.get("id") or "")
        except (ValueError, AttributeError):
            post_id = ""
        if not post_id:
            await self.redis.set(published_key, "uncertain", ex=2_592_000)
            await self._audit(event_id, "delivery_uncertain")
            return
        await self._audit(event_id, "published", post_id=post_id, image="yes" if image else "no")
