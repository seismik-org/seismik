/* Account-session explorer. No consumer credential is created or sent. */
"use strict";
const el = Object.fromEntries([...document.querySelectorAll("[id]")].map(node => [node.id, node]));
let user = null, events = [], visible = [], selectedId = null, map = null, layer = null;
let requestVersion = 0, busy = false, retryUntil = 0;
const markers = new Map();
const count = value => Number(value || 0).toLocaleString("es-CO");
const numeric = value => typeof value === "number" && Number.isFinite(value);
const magnitude = value => numeric(value) ? value.toLocaleString("es-CO", {minimumFractionDigits:1,maximumFractionDigits:1}) : "—";
function date(value) { const d = new Date(value); return Number.isNaN(d.valueOf()) ? "Fecha no disponible" : d.toLocaleString("es-CO", {dateStyle:"medium",timeStyle:"short"}); }
function message(text, error = false) { el.message.textContent = text; el.message.classList.toggle("error", error); }
function node(tag, text, className) { const n = document.createElement(tag); if (text != null) n.textContent = text; if (className) n.className = className; return n; }
function login() { sessionStorage.setItem("seismik-explore-return", "1"); location.assign("https://auth.seismik.org/id"); }
function located(event) { return numeric(event.latitude) && numeric(event.longitude) && Math.abs(event.latitude) <= 85 && Math.abs(event.longitude) <= 180 && !event.preliminary; }
function color(event) { return event.magnitude >= 6 ? "#d94e46" : event.magnitude >= 4 ? "#df990a" : "#248ac7"; }

async function api(path, options = {}) {
  const response = await fetch(path, {...options, credentials:"same-origin", cache:"no-store"});
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const error = new Error(typeof body.detail === "string" ? body.detail : `No se pudo consultar (${response.status}).`);
    error.status = response.status;
    error.retry = Math.max(1, Number(response.headers.get("Retry-After")) || 60);
    throw error;
  }
  return response.status === 204 ? null : response.json();
}

function resetData() {
  events = []; visible = []; selectedId = null;
  el["event-list"].replaceChildren(node("p", "Inicia sesión para ver el historial.", "empty-state"));
  el["event-count"].textContent = "0";
  el["event-detail"].replaceChildren(node("h2", "Selecciona un evento"), node("p", "El detalle y las fuentes aparecerán aquí."));
  layer?.clearLayers(); markers.clear();
  el["map-count"].textContent = "Sin datos cargados";
}

function updateAuth(identity) {
  user = identity;
  el.login.hidden = !!user; el.logout.hidden = !user; el["login-gate"].hidden = !!user;
  el["account-name"].textContent = user ? (user.name || user.email || "Tu cuenta Seismik") : "Inicia sesión para explorar";
  for (const id of ["days","magnitude","sources","limit","preliminary","search","local-search"]) el[id].disabled = !user || busy;
  if (!user) {
    requestVersion++; resetData();
    el["plan-name"].textContent = "—"; el["month-count"].textContent = "—";
    el["window-counts"].textContent = "Minuto — · Día —"; el["month-progress"].value = 0;
  }
}

function renderAccount(account) {
  const plan = account.plan, usage = account.quota_usage;
  el["plan-name"].textContent = plan.name;
  el["month-count"].textContent = `${count(usage.month.used)} / ${count(plan.requests_per_month)}`;
  el["month-progress"].value = Math.min(100, usage.month.used / Math.max(1, plan.requests_per_month) * 100);
  el["window-counts"].textContent = `Minuto ${count(usage.minute.used)}/${count(plan.requests_per_minute)} · Día ${count(usage.day.used)}/${count(plan.requests_per_day)}`;
  el["month-count"].title = `Se renueva: ${date(usage.month.resets_at)}`;
}

async function refreshAccount(version) {
  const account = await api("/v1/developer/account");
  if (version === requestVersion && user) renderAccount(account);
}

function initMap() {
  if (map || !window.L) return;
  map = L.map("map", {scrollWheelZoom:false}).setView([5,-73],5);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom:18, attribution:'&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a>',
  }).on("tileerror", () => { el["map-count"].textContent = "Mapa base no disponible; el historial sigue funcionando."; }).addTo(map);
  layer = L.layerGroup().addTo(map);
}

function fitMap() {
  const points = visible.filter(located).map(e => [e.latitude,e.longitude]);
  if (points.length && map) map.fitBounds(L.latLngBounds(points).pad(.12), {maxZoom:9});
}

function renderList() {
  const query = el["local-search"].value.trim().toLocaleLowerCase("es");
  visible = events.filter(event => {
    const match = `${event.place || ""} ${event.agency || ""}`.toLocaleLowerCase("es").includes(query);
    // This is a geographic browsing window, not an assertion of jurisdiction.
    const inRegion = event.latitude >= -5 && event.latitude <= 14.5 && event.longitude >= -83 && event.longitude <= -66;
    return match && (!el.colombia.checked || (located(event) && inRegion) || event.country_code === "CO");
  });
  el["event-count"].textContent = count(visible.length);
  const fragment = document.createDocumentFragment();
  visible.forEach(event => {
    const button = node("button", null, "event-card"); button.type = "button";
    button.dataset.id = event.event_id;
    button.classList.toggle("selected", event.event_id === selectedId);
    button.setAttribute("aria-pressed", String(event.event_id === selectedId));
    const mag = node("span", magnitude(event.magnitude), "event-magnitude");
    mag.append(node("small", event.magnitude_type || (event.preliminary ? "SEÑAL" : "MAG")));
    const copy = node("span", null, "event-copy");
    copy.append(node("strong", event.place || "Ubicación sin nombre"),
      node("span", `${date(event.detected_at || event.origin_time)} · ${event.agency || "Seismik"}`, "event-meta"),
      node("span", event.preliminary ? "Sin confirmar" : "Reporte de catálogo", `event-tag${event.preliminary ? " preliminary" : ""}`));
    button.append(mag,copy); button.addEventListener("click", () => selectEvent(event)); fragment.append(button);
  });
  el["event-list"].replaceChildren(visible.length ? fragment : node("p", "No hay eventos con estos filtros. Prueba otro período o magnitud.", "empty-state"));
  if (map) {
    layer.clearLayers(); markers.clear();
    visible.filter(located).forEach(event => {
      const marker = L.circleMarker([event.latitude,event.longitude], {radius:Math.max(5,Math.min(13,(event.magnitude || 2)*1.6)),color:"#ffffff",weight:1.5,fillColor:color(event),fillOpacity:.85});
      marker.bindTooltip(node("span", `${magnitude(event.magnitude)} · ${event.place || "Sismo"}`));
      marker.on("click", () => { selectEvent(event); document.querySelectorAll(".event-card").forEach(n => { if(n.dataset.id === event.event_id) n.scrollIntoView({block:"nearest"}); }); });
      marker.addTo(layer); markers.set(event.event_id, marker);
    });
  }
  const pins = visible.filter(located).length;
  el["map-count"].textContent = `${count(pins)} epicentros · ${count(visible.length - pins)} sin ubicación confirmada`;
  el["fit-map"].disabled = !pins || !map;
  if (selectedId && !visible.some(e => e.event_id === selectedId)) {
    selectedId = null; el["event-detail"].replaceChildren(node("h2", "Selecciona un evento"));
  }
}

function selectEvent(event) {
  selectedId = event.event_id;
  document.querySelectorAll(".event-card").forEach(n => { n.classList.toggle("selected", n.dataset.id === selectedId); n.setAttribute("aria-pressed", String(n.dataset.id === selectedId)); });
  const detail = el["event-detail"];
  detail.replaceChildren(node("p", event.preliminary ? "SEÑAL AUTOMÁTICA · SIN CONFIRMAR" : "REPORTE SÍSMICO", "eyebrow"), node("h2", event.place || "Ubicación sin nombre"));
  const data = node("dl", null, "detail-grid");
  const pairs = [["Magnitud",`${magnitude(event.magnitude)} ${event.magnitude_type || ""}`],
    ["Profundidad",numeric(event.depth_km) ? `${event.depth_km.toLocaleString("es-CO")} km` : "Sin determinar"],
    [event.preliminary ? "Detección (hora local)" : "Origen (hora local)",date(event.detected_at || event.origin_time)],
    ["Epicentro",located(event) ? `${event.latitude.toFixed(3)}, ${event.longitude.toFixed(3)}` : "Sin epicentro confirmado"],
    ["Agencia",event.agency || "Seismik"],["Revisión",event.review_status || "Según fuente"]];
  pairs.forEach(([label,value]) => { const item=node("div"); item.append(node("dt",label),node("dd",value)); data.append(item); }); detail.append(data);
  if (event.preliminary) detail.append(node("p", "Una señal multiestación no demuestra que haya ocurrido un sismo. El centro de las estaciones no se presenta como epicentro."));
  if (event.own_magnitude) {
    const own = event.own_magnitude;
    detail.append(node("p", numeric(own.value) ? `Magnitud propia ${magnitude(own.value)} ${own.scale || "ML"} · ${own.validation_status === "validated" ? "validada según registro" : "beta sin validación científica"}` : "Magnitud propia no disponible para este evento."));
  }
  const reports = event.source_reports?.length ? event.source_reports : [event];
  reports.forEach(report => {
    const row = node("div", null, "source-report");
    row.append(node("strong", `${report.agency || report.source_id || "Seismik"} · ${magnitude(report.magnitude)} ${report.magnitude_type || ""}`));
    if (report.attribution) row.append(node("p", report.attribution));
    try {
      const url = new URL(report.official_url);
      if (url.protocol === "https:") {
        const a = node("a", "Ver reporte original ↗"); a.href = url.href; a.target = "_blank"; a.rel = "noopener noreferrer"; row.append(node("br"),a);
      }
    } catch (_) { /* A missing source URL is never turned into a link. */ }
    detail.append(row);
  });
  const marker = markers.get(event.event_id);
  if (marker && map) { map.panTo(marker.getLatLng()); marker.openTooltip(); }
}

async function search(event) {
  event?.preventDefault();
  if (!user || busy) return;
  if (Date.now() < retryUntil) { message(`Has alcanzado un límite. Vuelve a consultar después de ${date(retryUntil)}.`,true); return; }
  const version = ++requestVersion;
  busy = true; updateAuth(user); el.search.textContent = "Consultando…";
  el["event-list"].setAttribute("aria-busy","true"); message("Consultando las fuentes; se utiliza 1 consulta de eventos.");
  const sources = el.sources.value + (el.preliminary.checked ? ",seismik_seedlink_preliminary" : "");
  const params = new URLSearchParams({sources,days:el.days.value,minimum_magnitude:el.magnitude.value,limit:el.limit.value});
  try {
    const result = await api(`/v1/developer/explore/history?${params}`);
    if (version !== requestVersion || !user) return;
    events = Array.isArray(result.events) ? result.events : [];
    initMap(); renderList(); fitMap();
    const errors = Array.isArray(result.errors) ? result.errors : [];
    const unavailable = errors.map(e => e.source_id || e.source || "una fuente").join(", ");
    message(`Actualizado: ${date(result.generated_at)} · ${count(events.length)} eventos recibidos${events.length >= Number(el.limit.value) ? " · Se alcanzó el límite de resultados; acota los filtros." : "."}${errors.length ? ` Hay fuentes sin respuesta: ${unavailable}. El historial puede estar incompleto.` : ""}`,errors.length > 0);
  } catch (error) {
    if (version !== requestVersion) return;
    if (error.status === 401) { updateAuth(null); message("Tu sesión venció. Entra de nuevo para continuar.",true); }
    else if (error.status === 429) { retryUntil = Date.now()+error.retry*1000; message(`Alcanzaste un límite de tu plan. Puedes volver a consultar después de ${date(retryUntil)}.`,true); }
    else message(`No se pudo actualizar el historial. ${events.length ? "Se conservan los datos anteriores. " : ""}${error.status === 503 ? "El servicio no está disponible temporalmente." : error.message}`,true);
  } finally {
    busy = false; el.search.textContent = "Consultar historial"; el["event-list"].removeAttribute("aria-busy");
    updateAuth(user);
    if (user && version === requestVersion) await refreshAccount(version).catch(() => {});
  }
}

async function boot(autoSearch = true) {
  const version = ++requestVersion;
  try {
    const identity = await api("/v1/oauth/session");
    if (version !== requestVersion) return;
    updateAuth(identity); await refreshAccount(version);
    if (autoSearch && version === requestVersion) await search();
  } catch (error) { if (version === requestVersion) { updateAuth(null); message(error.status === 401 ? "Inicia sesión para explorar con tu plan." : "No pudimos comprobar tu sesión. Vuelve a intentarlo.", error.status !== 401); } }
}
el.login.addEventListener("click",login); el["gate-login"].addEventListener("click",login);
el.logout.addEventListener("click",async () => { try { await api("/v1/oauth/logout",{method:"POST"}); updateAuth(null); message("Sesión cerrada."); } catch (_) { message("No se pudo cerrar la sesión. Inténtalo otra vez.",true); } });
el.filters.addEventListener("submit",search); el["local-search"].addEventListener("input",renderList); el.colombia.addEventListener("change",renderList); el["fit-map"].addEventListener("click",fitMap);
window.addEventListener("pageshow",event => { if (event.persisted) { updateAuth(null); boot(false); } });
boot();
