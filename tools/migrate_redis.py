"""Copia claves Redis entre dos instancias sin exponer valores en la consola.

Uso para el corte de Memorystore::

    python tools/migrate_redis.py --source redis://ORIGEN:6379/0 \
        --target redis://DESTINO:6379/0

El script usa DUMP/RESTORE, por lo que preserva estructuras Redis y sus TTL.
Se puede ejecutar dos veces: una previa y otra justo durante el corte.
"""
from __future__ import annotations

import argparse
import sys

from redis import Redis


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="URL Redis origen")
    parser.add_argument("--target", required=True, help="URL Redis destino")
    parser.add_argument("--dry-run", action="store_true", help="No escribe en el destino")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = Redis.from_url(args.source, decode_responses=False)
    target = Redis.from_url(args.target, decode_responses=False)
    source.ping()
    target.ping()

    copied = skipped = 0
    for key in source.scan_iter(count=500):
        payload = source.dump(key)
        ttl = source.pttl(key)
        if payload is None or ttl == -2:
            skipped += 1
            continue
        if not args.dry_run:
            # -1 significa sin expiración; RESTORE lo representa con TTL cero.
            target.restore(key, 0 if ttl < 0 else ttl, payload, replace=True)
        copied += 1
    print(f"keys_copied={copied} keys_skipped={skipped} dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
