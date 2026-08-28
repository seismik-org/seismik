from __future__ import annotations

from reporting.schemas import AgencyRoute

COUNTRY_ROUTES: dict[str, AgencyRoute] = {
    "CO": AgencyRoute(
        agency_id="sgc",
        agency_name="Servicio Geológico Colombiano",
        country_code="CO",
        official_url="https://sismosentido.sgc.gov.co/",
    ),
    "ES": AgencyRoute(
        agency_id="ign_es",
        agency_name="Instituto Geográfico Nacional de España",
        country_code="ES",
        official_url="https://www.ign.es/web/resources/cuestionario-macrosismico/",
    ),
    "CA": AgencyRoute(
        agency_id="nrcan",
        agency_name="Earthquakes Canada / Natural Resources Canada",
        country_code="CA",
        official_url="https://www.earthquakescanada.nrcan.gc.ca/dyfi-lavr/index-en.php",
    ),
}

USGS_GLOBAL = AgencyRoute(
    agency_id="usgs_dyfi",
    agency_name="USGS Did You Feel It?",
    country_code=None,
    official_url="https://earthquake.usgs.gov/data/dyfi/",
)


def routes_for(
    country_code: str,
    official_event_id: str | None,
    selected_agency_ids: tuple[str, ...] | None = None,
) -> tuple[AgencyRoute, ...]:
    country = country_code.upper()
    routes: list[AgencyRoute] = []
    local = COUNTRY_ROUTES.get(country)
    if local is not None:
        routes.append(local)
    usgs = USGS_GLOBAL
    if official_event_id and official_event_id.replace("_", "").replace("-", "").isalnum():
        usgs = usgs.model_copy(
            update={
                "official_url": (
                    "https://earthquake.usgs.gov/earthquakes/eventpage/"
                    f"{official_event_id}/tellus"
                )
            }
        )
    routes.append(usgs)
    if selected_agency_ids is None:
        return tuple(routes)
    selected = set(selected_agency_ids)
    return tuple(route for route in routes if route.agency_id in selected)
