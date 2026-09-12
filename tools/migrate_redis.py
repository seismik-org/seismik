"""Copia claves Redis entre dos instancias sin exponer valores en la consola.

Uso para el corte de Memorystore::

    python tools/migrate_redis.py --source redis://ORIGEN:6379/0 \
        --target redis://DESTINO:6379/0

El script preserva estructuras Redis y sus TTL sin usar RDB/DUMP: Memorystore
puede estar en una versión Redis menor que la instancia origen, y un RDB más
nuevo no se puede restaurar en una versión anterior. Se puede ejecutar dos
veces: una previa y otra justo durante el corte.
"""
from __future__ import annotations

import argparse

from redis import Redis


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="URL Redis origen")
    parser.add_argument("--target", required=True, help="URL Redis destino")
    parser.add_argument("--dry-run", action="store_true", help="No escribe en el destino")
    parser.add_argument(
        "--flush-target",
        action="store_true",
        help="Vacía el destino antes de copiar; úsalo solo en una instancia nueva",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = Redis.from_url(args.source, decode_responses=False)
    target = Redis.from_url(args.target, decode_responses=False)
    source.ping()
    target.ping()

    if args.flush_target and not args.dry_run:
        target.flushdb()

    copied = skipped = 0
    for key in source.scan_iter(count=500):
        ttl = source.pttl(key)
        key_type = source.type(key)
        if key_type == b"none" or ttl == -2:
            skipped += 1
            continue
        if not args.dry_run:
            _copy_key(source, target, key, key_type)
            if ttl >= 0:
                target.pexpire(key, ttl)
        copied += 1
    print(f"keys_copied={copied} keys_skipped={skipped} dry_run={args.dry_run}")
    return 0


def _copy_key(source: Redis, target: Redis, key: bytes, key_type: bytes) -> None:
    """Copia tipos nativos con comandos compatibles entre Redis 7 y 8."""

    target.delete(key)
    if key_type == b"string":
        target.set(key, source.get(key))
    elif key_type == b"hash":
        values = source.hgetall(key)
        if values:
            target.hset(key, mapping=values)
    elif key_type == b"set":
        values = source.smembers(key)
        if values:
            target.sadd(key, *values)
    elif key_type == b"list":
        values = source.lrange(key, 0, -1)
        if values:
            target.rpush(key, *values)
    elif key_type == b"zset":
        values = source.zrange(key, 0, -1, withscores=True)
        if values:
            target.zadd(key, {member: score for member, score in values})
    elif key_type == b"stream":
        for message_id, fields in source.xrange(key, min="-", max="+"):
            target.xadd(key, fields, id=message_id)
        for group in source.xinfo_groups(key):
            try:
                target.xgroup_create(key, group["name"], id=group["last-delivered-id"], mkstream=True)
            except Exception as exc:  # no se pierde el stream por un grupo ya creado
                if "BUSYGROUP" not in str(exc):
                    raise
    else:
        raise RuntimeError(f"Redis type not supported for migration: {key_type!r}")


if __name__ == "__main__":
    raise SystemExit(main())
