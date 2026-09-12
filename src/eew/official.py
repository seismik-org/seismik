from __future__ import annotations

import json
import logging
import math
import re
import threading
import uuid
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import requests

from eew.config import OfficialReportsSettings
from eew.models import (
    EarthquakeCandidate,
    OfficialReport,
    OfficialReportUpdate,
    utc_now_iso,
)

LOGGER = logging.getLogger(__name__)
USER_AGENT = "seismik-detector/0.3 (+official-report-enrichment)"


@dataclass(frozen=True)
class OfficialSource:
    id: str
    agency: str
    jurisdiction: str
    countries: tuple[str, ...]
    adapter: str
    endpoint: str
    official_site: str
    priority: int
    enabled: bool = True
    global_fallback: bool = False
    attribution: str | None = None


def load_sources(path: str | Path) -> tuple[OfficialSource, ...]:
    with Path(path).open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    return tuple(
        OfficialSource(
            **{
                **item,
                "countries": tuple(code.upper() for code in item.get("countries", [])),
            }
        )
        for item in raw["sources"]
    )


class OfficialApiClient:
    """Normaliza catálogos gubernamentales heterogéneos a OfficialReport."""

    def __init__(
        self,
        source: OfficialSource,
        timeout_seconds: float,
        session: requests.Session | None = None,
    ):
        self.source = source
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def fetch(self, start: datetime, end: datetime) -> list[OfficialReport]:
        adapter = getattr(self, f"_fetch_{self.source.adapter}", None)
        if adapter is None:
            raise ValueError(f"Adapter oficial no soportado: {self.source.adapter}")
        return adapter(start, end)

    def _get(self, url: str | None = None, **kwargs: Any) -> requests.Response:
        response = self.session.get(
            url or self.source.endpoint, timeout=self.timeout_seconds, **kwargs
        )
        response.raise_for_status()
        return response

    def _report(
        self,
        event_id: Any,
        origin_time: Any,
        latitude: Any,
        longitude: Any,
        *,
        depth_km: Any = None,
        magnitude: Any = None,
        magnitude_type: Any = None,
        place: Any = None,
        review_status: Any = None,
        updated_at: Any = None,
        official_url: str | None = None,
        tsunami: bool | None = None,
        felt: Any = None,
    ) -> OfficialReport | None:
        try:
            origin = _parse_time(origin_time)
            lat = float(latitude)
            lon = float(longitude)
        except (TypeError, ValueError, OverflowError):
            return None
        return OfficialReport(
            source_id=self.source.id,
            agency=self.source.agency,
            jurisdiction=self.source.jurisdiction,
            official_event_id=str(event_id),
            origin_time=_iso(origin),
            updated_at=_iso(_parse_time(updated_at)) if updated_at is not None else None,
            latitude=lat,
            longitude=lon,
            depth_km=_float_or_none(depth_km),
            magnitude=_float_or_none(magnitude),
            magnitude_type=str(magnitude_type) if magnitude_type else None,
            place=str(place) if place else None,
            review_status=str(review_status) if review_status else None,
            official_url=official_url or self.source.official_site,
            attribution=self.source.attribution,
            tsunami=tsunami,
            felt=str(felt) if felt not in (None, "") else None,
        )

    def _fetch_fdsn_geojson(self, start: datetime, end: datetime) -> list[OfficialReport]:
        payload = self._get(
            params={
                "format": "geojson",
                # INGV rechaza fracciones de segundo; USGS acepta este subconjunto.
                "starttime": start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
                "endtime": end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
                "orderby": "time",
                "limit": 200,
            }
        ).json()
        reports = []
        for feature in payload.get("features", []):
            props = feature.get("properties", {})
            coordinates = (feature.get("geometry") or {}).get("coordinates", [])
            if len(coordinates) < 2:
                continue
            detail = props.get("url") or props.get("detail") or self.source.official_site
            report = self._report(
                feature.get("id") or props.get("eventId"),
                props.get("time"),
                coordinates[1],
                coordinates[0],
                depth_km=coordinates[2] if len(coordinates) > 2 else None,
                magnitude=props.get("mag"),
                magnitude_type=props.get("magType"),
                place=props.get("place") or props.get("flynn_region"),
                review_status=props.get("status"),
                updated_at=(
                    props.get("updated")
                    or props.get("lastUpdate")
                    or props.get("geojson_creationTime")
                ),
                official_url=detail,
                tsunami=bool(props["tsunami"]) if props.get("tsunami") is not None else None,
                felt=props.get("felt"),
            )
            if report:
                reports.append(report)
        return reports

    def _fetch_geonet_geojson(self, _start: datetime, _end: datetime) -> list[OfficialReport]:
        payload = self._get(
            params={"MMI": -1}, headers={"Accept": "application/vnd.geo+json;version=2"}
        ).json()
        reports = []
        for feature in payload.get("features", []):
            props = feature.get("properties", {})
            coordinates = (feature.get("geometry") or {}).get("coordinates", [])
            if len(coordinates) < 2:
                continue
            event_id = props.get("publicID")
            report = self._report(
                event_id,
                props.get("time"),
                coordinates[1],
                coordinates[0],
                depth_km=props.get("depth"),
                magnitude=props.get("magnitude"),
                place=props.get("locality"),
                review_status=props.get("quality"),
                official_url=f"https://www.geonet.org.nz/earthquake/{event_id}",
                felt=props.get("mmi"),
            )
            if report:
                reports.append(report)
        return reports

    def _fetch_bmkg_json(self, _start: datetime, _end: datetime) -> list[OfficialReport]:
        payload = self._get().json().get("Infogempa", {})
        events = payload.get("gempa", [])
        if isinstance(events, dict):
            events = [events]
        reports = []
        for event in events:
            coordinates = str(event.get("Coordinates", "")).split(",")
            if len(coordinates) != 2:
                continue
            origin = event.get("DateTime") or f"{event.get('Tanggal')} {event.get('Jam')}"
            event_id = event.get("DateTime") or f"bmkg-{origin}"
            potential = str(event.get("Potensi", "")).strip()
            report = self._report(
                event_id,
                origin,
                coordinates[0],
                coordinates[1],
                depth_km=_number_from_text(event.get("Kedalaman")),
                magnitude=event.get("Magnitude"),
                place=event.get("Wilayah"),
                review_status="published",
                official_url=self.source.official_site,
                tsunami=("tidak" not in potential.lower()) if potential else None,
                felt=event.get("Dirasakan"),
            )
            if report:
                reports.append(report)
        return reports

    def _fetch_jma_atom(self, start: datetime, end: datetime) -> list[OfficialReport]:
        root = ET.fromstring(self._get().content)
        atom = {"a": "http://www.w3.org/2005/Atom"}
        reports = []
        seen: set[str] = set()
        for entry in root.findall("a:entry", atom):
            link = entry.find("a:link", atom)
            if link is None or not link.attrib.get("href"):
                continue
            updated_node = entry.find("a:updated", atom)
            updated = _parse_time(updated_node.text) if updated_node is not None else end
            if updated < start - timedelta(minutes=15) or updated > end + timedelta(minutes=15):
                continue
            bulletin_url = link.attrib["href"]
            bulletin = ET.fromstring(self._get(bulletin_url).content)
            event_id = _first_text(bulletin, "EventID")
            origin = _first_text(bulletin, "OriginTime")
            coordinate = _first_text(bulletin, "Coordinate")
            magnitude_node = _first_element(bulletin, "Magnitude")
            hypocenter = _first_element(bulletin, "Hypocenter")
            if not event_id or event_id in seen or not origin or not coordinate or hypocenter is None:
                continue
            numbers = re.findall(r"[+-]\d+(?:\.\d+)?", coordinate)
            if len(numbers) < 2:
                continue
            depth = abs(float(numbers[2])) / 1000 if len(numbers) > 2 else None
            place = _first_text(hypocenter, "Name")
            report = self._report(
                event_id,
                origin,
                numbers[0],
                numbers[1],
                depth_km=depth,
                magnitude=magnitude_node.text if magnitude_node is not None else None,
                magnitude_type=(magnitude_node.attrib.get("type") if magnitude_node is not None else None),
                place=place,
                review_status="published",
                updated_at=updated,
                official_url=bulletin_url,
            )
            if report:
                seen.add(event_id)
                reports.append(report)
        return reports

    def _fetch_sgc_geojson(self, start: datetime, end: datetime) -> list[OfficialReport]:
        start_utc = start.replace(tzinfo=timezone.utc) if start.tzinfo is None else start.astimezone(timezone.utc)
        end_utc = end.replace(tzinfo=timezone.utc) if end.tzinfo is None else end.astimezone(timezone.utc)
        payload = self._get(
            # El endpoint del SGC exige fecha y hora ISO-8601. Con sólo la
            # fecha responde 200 pero incluye un objeto ``error`` y el
            # agregador terminaba interpretándolo como un catálogo vacío.
            params={
                "startdate": start_utc.strftime("%Y-%m-%dT%H:%M:%S"),
                "enddate": end_utc.strftime("%Y-%m-%dT%H:%M:%S"),
            }
        ).json()
        if isinstance(payload, dict) and payload.get("error"):
            detail = payload["error"]
            raise RuntimeError(f"SGC devolvió un error de catálogo: {detail}")
        reports = []
        for feature in payload.get("features", []):
            props = feature.get("properties", {})
            coordinates = (feature.get("geometry") or {}).get("coordinates", [])
            if len(coordinates) < 2:
                continue
            event_id = feature.get("id")
            report = self._report(
                event_id,
                props.get("utcTime"),
                coordinates[1],
                coordinates[0],
                depth_km=props.get("depth") or (coordinates[2] if len(coordinates) > 2 else None),
                magnitude=props.get("mag"),
                magnitude_type=props.get("magType"),
                place=props.get("place"),
                review_status=props.get("status"),
                updated_at=props.get("updated"),
                official_url=f"https://www.sgc.gov.co/detallesismo/{event_id}/resumen",
                felt=props.get("cdi") or props.get("mmi"),
            )
            if report:
                reports.append(report)
        return reports

    def _fetch_igp_arcgis(self, _start: datetime, _end: datetime) -> list[OfficialReport]:
        payload = self._get(
            params={
                "where": "fechaevento IS NOT NULL",
                "outFields": "*",
                "returnGeometry": "true",
                "orderByFields": "fechaevento DESC",
                "resultRecordCount": 100,
                "f": "geojson",
            }
        ).json()
        reports = []
        for feature in payload.get("features", []):
            props = feature.get("properties", {})
            coordinates = (feature.get("geometry") or {}).get("coordinates", [])
            if len(coordinates) < 2:
                continue
            event_id = props.get("code") or feature.get("id")
            report = self._report(
                event_id,
                props.get("fechaevento"),
                props.get("lat", coordinates[1]),
                props.get("lon", coordinates[0]),
                depth_km=props.get("prof"),
                magnitude=props.get("magnitud"),
                place=props.get("ref"),
                review_status="reported",
                official_url=f"https://ultimosismo.igp.gob.pe/evento/{event_id}",
                felt=props.get("int_"),
            )
            if report:
                reports.append(report)
        return reports


class OfficialReportService:
    """Consulta reportes después de alertar; nunca bloquea el hilo SeedLink."""

    def __init__(
        self,
        settings: OfficialReportsSettings,
        publish: Callable[[OfficialReportUpdate], None],
    ):
        self.settings = settings
        self.publish = publish
        self.sources = load_sources(settings.sources_file) if settings.enabled else ()
        self._stop = threading.Event()
        self._executor = ThreadPoolExecutor(
            max_workers=settings.max_concurrent_candidates,
            thread_name_prefix="official-report",
        )
        self._slots = threading.BoundedSemaphore(settings.max_concurrent_candidates)

    def submit(self, candidate: EarthquakeCandidate) -> None:
        if not self.settings.enabled:
            return
        if not self._slots.acquire(blocking=False):
            LOGGER.error(
                "Capacidad de reportes oficiales agotada; candidato omitido event_id=%s",
                candidate.event_id,
            )
            return
        self._executor.submit(self._poll_and_release, candidate)

    def close(self) -> None:
        self._stop.set()
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _poll_candidate(self, candidate: EarthquakeCandidate) -> None:
        if self._stop.wait(self.settings.initial_delay_seconds):
            return
        known: dict[str, OfficialReport] = {}
        last_snapshot: tuple[tuple[str, str, str | None], ...] = ()
        delays = (0.0, *self.settings.poll_intervals_seconds)
        for delay in delays:
            if delay and self._stop.wait(delay):
                return
            for source in self._eligible_sources(candidate):
                try:
                    client = OfficialApiClient(source, self.settings.request_timeout_seconds)
                    start, end = _candidate_query_window(candidate, self.settings)
                    matches = [
                        matched
                        for report in client.fetch(start, end)
                        if (matched := match_report(candidate, report, self.settings)) is not None
                    ]
                    if matches:
                        # Un solo evento por organismo: el más cercano en tiempo
                        # y espacio. Evita mezclar una réplica dentro de la ventana.
                        known[source.id] = min(
                            matches,
                            key=lambda item: (
                                item.origin_time_delta_seconds or 0.0,
                                item.distance_from_station_centroid_km or 0.0,
                            ),
                        )
                except Exception:
                    LOGGER.warning("Consulta oficial falló source=%s", source.id, exc_info=True)
            if known:
                ordered = tuple(sorted(known.values(), key=self._preference_key))
                snapshot = tuple(
                    (item.source_id, item.official_event_id, item.updated_at) for item in ordered
                )
                if snapshot == last_snapshot:
                    continue
                last_snapshot = snapshot
                update = OfficialReportUpdate(
                    event_id=str(uuid.uuid4()),
                    candidate_event_id=candidate.event_id,
                    type="official_report_update",
                    status="official_report_available",
                    matched_at=utc_now_iso(),
                    preferred_report=ordered[0],
                    reports=ordered,
                )
                self.publish(update)

    def _poll_and_release(self, candidate: EarthquakeCandidate) -> None:
        try:
            self._poll_candidate(candidate)
        finally:
            self._slots.release()

    def _eligible_sources(self, candidate: EarthquakeCandidate) -> tuple[OfficialSource, ...]:
        countries = set(candidate.country_codes)
        return tuple(
            source
            for source in self.sources
            if source.enabled and (source.global_fallback or countries.intersection(source.countries))
        )

    def _preference_key(self, report: OfficialReport) -> tuple[int, float, float]:
        source = next(item for item in self.sources if item.id == report.source_id)
        return (
            -source.priority,
            report.origin_time_delta_seconds or 0.0,
            report.distance_from_station_centroid_km or 0.0,
        )


def match_report(
    candidate: EarthquakeCandidate,
    report: OfficialReport,
    settings: OfficialReportsSettings,
) -> OfficialReport | None:
    from dataclasses import replace

    trigger_time = min(_parse_time(item.trigger_time) for item in candidate.stations)
    delta = abs((_parse_time(report.origin_time) - trigger_time).total_seconds())
    if delta > settings.max_origin_time_delta_seconds:
        return None
    distance = None
    if candidate.estimated_latitude is not None and candidate.estimated_longitude is not None:
        distance = _haversine_km(
            candidate.estimated_latitude,
            candidate.estimated_longitude,
            report.latitude,
            report.longitude,
        )
        if distance > settings.max_distance_km:
            return None
    return replace(
        report,
        origin_time_delta_seconds=round(delta, 3),
        distance_from_station_centroid_km=round(distance, 3) if distance is not None else None,
    )


def _candidate_query_window(
    candidate: EarthquakeCandidate, settings: OfficialReportsSettings
) -> tuple[datetime, datetime]:
    trigger_time = min(_parse_time(item.trigger_time) for item in candidate.stations)
    margin = timedelta(seconds=settings.max_origin_time_delta_seconds)
    # Una consulta acotada evita descargar anos de catalogo cuando se reproduce
    # un evento historico. Para candidatos en vivo cubre exactamente el mismo
    # margen temporal que posteriormente acepta ``match_report``.
    return trigger_time - margin, trigger_time + margin


def _parse_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        seconds = float(value) / 1000 if abs(float(value)) > 10_000_000_000 else float(value)
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _number_from_text(value: Any) -> float | None:
    match = re.search(r"-?\d+(?:\.\d+)?", str(value or ""))
    return float(match.group()) if match else None


def _first_element(root: ET.Element, local_name: str) -> ET.Element | None:
    return next((item for item in root.iter() if item.tag.split("}")[-1] == local_name), None)


def _first_text(root: ET.Element, local_name: str) -> str | None:
    element = _first_element(root, local_name)
    return element.text.strip() if element is not None and element.text else None


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
