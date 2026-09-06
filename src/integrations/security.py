from __future__ import annotations

import hashlib
import hmac


def derive_webhook_secret(master_secret: str, webhook_id: str) -> str:
    """Obtiene un secreto estable sin persistirlo como texto en Redis."""

    material = hmac.new(master_secret.encode(), webhook_id.encode(), hashlib.sha256).hexdigest()
    return f"swh_{material}"
