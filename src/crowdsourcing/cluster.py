from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import h3  # type: ignore[import-untyped]
from redis.asyncio import Redis

from api.config import AppSettings
from api.schemas import ShakePing


# KEYS: N ventanas H3, N locks de cooldown y el stream de candidatos.
# La operacion es atomica en Redis standalone/Sentinel. Redis Cluster no puede
# ejecutar este script sobre slots distintos; vea la nota de despliegue del README.
CLUSTER_LUA = """
local cell_count = tonumber(ARGV[1])
local window_start = ARGV[2]
local event_time = ARGV[3]
local device_id = ARGV[4]
local window_ttl = ARGV[5]
local unique_devices = {}
local unique_count = 0

for index = 1, cell_count do
  redis.call('ZREMRANGEBYSCORE', KEYS[index], '-inf', window_start)
end

-- Un telefono pertenece a una celda primaria. ZADD actualiza su timestamp y
-- evita que una rafaga repetida infle el quorum.
redis.call('ZADD', KEYS[1], event_time, device_id)
redis.call('EXPIRE', KEYS[1], window_ttl)

for index = 1, cell_count do
  local members = redis.call('ZRANGE', KEYS[index], 0, -1)
  for _, member in ipairs(members) do
    if not unique_devices[member] then
      unique_devices[member] = true
      unique_count = unique_count + 1
    end
  end
end

local triggered = 0
local stream_id = ''
if unique_count >= tonumber(ARGV[6]) then
  local blocked = false
  for index = 1, cell_count do
    if redis.call('EXISTS', KEYS[cell_count + index]) == 1 then
      blocked = true
      break
    end
  end

  if not blocked then
    -- Bloquear todo el disco k=1 evita dos alertas del mismo cluster cuando
    -- llegan pings simultaneos a celdas adyacentes.
    for index = 1, cell_count do
      redis.call('SET', KEYS[cell_count + index], ARGV[7], 'EX', ARGV[8])
    end
    local payload = cjson.encode({
      event_id = ARGV[7],
      type = 'crowdsourced_earthquake_candidate',
      status = 'unlocated_unreviewed',
      zone_id = ARGV[9],
      detected_at = ARGV[10],
      estimated_latitude = tonumber(ARGV[11]),
      estimated_longitude = tonumber(ARGV[12]),
      pga_threshold_g = tonumber(ARGV[13]),
      device_count = unique_count,
      window_seconds = tonumber(ARGV[14]),
      source = 'mobile_accelerometer_h3_cluster'
    })
    stream_id = redis.call(
      'XADD', KEYS[(cell_count * 2) + 1], 'MAXLEN', '~', ARGV[15], '*',
      'payload', payload, 'event_id', ARGV[7],
      'event_type', 'crowdsourced_earthquake_candidate'
    )
    triggered = 1
  end
end
return {unique_count, triggered, stream_id}
"""


@dataclass(frozen=True)
class H3Neighborhood:
    primary: str
    cells: tuple[str, ...]
    center_latitude: float
    center_longitude: float


@dataclass(frozen=True)
class ClusterResult:
    cell_id: str
    device_count: int
    triggered: bool
    stream_id: str | None


class CrowdClusterEngine:
    def __init__(self, redis: Redis, settings: AppSettings):
        self.redis = redis
        self.settings = settings

    def neighborhood_for(self, latitude: float, longitude: float) -> H3Neighborhood:
        primary = h3.latlng_to_cell(
            latitude, longitude, self.settings.crowd_h3_resolution
        )
        disk = h3.grid_disk(primary, 1)
        # La primaria va primero porque el Lua inserta el ping solo en KEYS[1].
        cells = (primary, *sorted(cell for cell in disk if cell != primary))
        center_latitude, center_longitude = h3.cell_to_latlng(primary)
        return H3Neighborhood(
            primary=primary,
            cells=cells,
            center_latitude=center_latitude,
            center_longitude=center_longitude,
        )

    def cell_for(self, latitude: float, longitude: float) -> tuple[str, float, float]:
        neighborhood = self.neighborhood_for(latitude, longitude)
        return (
            neighborhood.primary,
            neighborhood.center_latitude,
            neighborhood.center_longitude,
        )

    async def add(self, ping: ShakePing) -> ClusterResult:
        neighborhood = self.neighborhood_for(ping.lat, ping.lon)
        event_id = str(uuid.uuid4())
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        event_time = ping.timestamp_seconds
        window_start = event_time - self.settings.crowd_window_seconds
        expiry = max(5, math.ceil(self.settings.crowd_window_seconds * 3))
        zone_id = f"h3:{neighborhood.primary}"
        window_keys = [f"seismik:crowd:window:{cell}" for cell in neighborhood.cells]
        cooldown_keys = [f"seismik:crowd:cooldown:{cell}" for cell in neighborhood.cells]
        keys = [*window_keys, *cooldown_keys, self.settings.candidate_stream]

        result = await self.redis.eval(
            CLUSTER_LUA,
            len(keys),
            *keys,
            len(neighborhood.cells),
            window_start,
            event_time,
            ping.device_id,
            expiry,
            self.settings.crowd_min_devices,
            event_id,
            self.settings.crowd_trigger_cooldown_seconds,
            zone_id,
            now_iso,
            neighborhood.center_latitude,
            neighborhood.center_longitude,
            self.settings.crowd_pga_threshold_g,
            self.settings.crowd_window_seconds,
            self.settings.stream_maxlen,
        )
        stream_id = result[2] or None
        if isinstance(stream_id, bytes):
            stream_id = stream_id.decode()
        return ClusterResult(
            cell_id=neighborhood.primary,
            device_count=int(result[0]),
            triggered=bool(int(result[1])),
            stream_id=stream_id,
        )
