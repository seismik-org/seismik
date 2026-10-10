"use strict";
// Pestaña «Reportes» de admin.seismik.org. La API vive en el mismo origen (el
// Worker envía /v1/* a la API) y admin.js decide el acceso; los utilitarios de
// aquí ($, element, api, dateTime, ago) también los usa admin.js.
const $ = selector => document.querySelector(selector);
const countries = new Intl.DisplayNames(["es"], {type:"region"});
const dateTime = value => new Date(value).toLocaleString("es", {dateStyle:"medium", timeStyle:"short"});
const ROMAN = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"];
const PLAUSIBILITY = {plausible:"Plausible", implausible:"Poco plausible", unknown:"Sin comparar"};
const REVIEW = {valid:"Válido", dismissed:"Descartado"};
const SEVERITY = {none:"Sin daños", minor:"Leves", moderate:"Moderados", severe:"Graves", collapse:"Colapso"};
let reports = [];

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function country(code) {
  if (!code || code === "ZZ") return "País desconocido";
  try { return countries.of(code) || code; } catch { return code; }
}
function placeName(place) {
  if (!place) return "Lugar sin descripción";
  return place === place.toUpperCase()
    ? place.toLocaleLowerCase("es").replace(/(^|[\s,(/-])(\p{L})/gu, (_, gap, letter) => gap + letter.toLocaleUpperCase("es"))
    : place;
}
function ago(value) {
  const minutes = Math.round((Date.now() - new Date(value)) / 60000);
  if (minutes < 60) return `hace ${Math.max(minutes, 0)} min`;
  if (minutes < 1440) return `hace ${Math.round(minutes / 60)} h`;
  return `hace ${Math.round(minutes / 1440)} d`;
}

async function api(path, options = {}) {
  const headers = {Accept:"application/json"};
  if (options.method && options.method !== "GET") headers["X-Seismik-Admin"] = "1";
  if (options.approval) headers["X-Seismik-Admin-Approval"] = options.approval;
  if (options.body) headers["Content-Type"] = "application/json";
  const response = await fetch(path, {...options, headers, credentials:"include", cache:"no-store"});
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(typeof data.detail === "string" ? data.detail : `Error ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return data;
}

async function loadReports() {
  const epoch = typeof adminEpoch === "undefined" ? 0 : adminEpoch;
  $("#reports-status").textContent = "Cargando reportes…";
  try {
    const data = await api("/v1/reports/admin/reports?limit=2000");
    if (typeof adminEpoch !== "undefined" && epoch !== adminEpoch) return false;
    reports = data.reports;
    $("#export").disabled = false;
    $("#reports-status").textContent = "";
    render();
    return true;
  } catch (error) {
    if (typeof accessError === "function" && accessError(error)) return false;
    $("#reports-status").textContent = `No se pudieron cargar los reportes: ${error.message}`;
    return false;
  }
}

function reviewStatus(item) { return item.review?.status || "pending"; }
function matches(item) {
  const value = id => $(id).value;
  if (value("#filter-source") !== "all" && item.source !== value("#filter-source")) return false;
  if (value("#filter-kind") !== "all" && item.kind !== value("#filter-kind")) return false;
  if (value("#filter-plausibility") !== "all" && item.plausibility.status !== value("#filter-plausibility")) return false;
  if (value("#filter-review") !== "all" && reviewStatus(item) !== value("#filter-review")) return false;
  const query = $("#filter-q").value.trim().toLocaleLowerCase("es");
  if (!query) return true;
  return [item.event?.place, country(item.report.country_code), item.report.country_code, item.report.report_id, item.report.earthquake_event_id]
    .some(text => (text || "").toLocaleLowerCase("es").includes(query));
}

function renderStats() {
  const day = Date.now() - 86400000;
  const stats = [
    ["Total", reports.length],
    ["App", reports.filter(item => item.source === "app").length],
    ["ifeltit", reports.filter(item => item.source === "web").length],
    ["Poco plausibles", reports.filter(item => item.plausibility.status === "implausible").length, "warn"],
    ["Sin revisar", reports.filter(item => reviewStatus(item) === "pending").length],
    ["Últimas 24 h", reports.filter(item => new Date(item.received_at) > day).length],
  ];
  $("#stats").replaceChildren(...stats.map(([label, value, tone]) => {
    const item = element("li", `report-stat${tone && value ? ` ${tone}` : ""}`);
    item.append(element("strong", "", String(value)), element("span", "", label));
    return item;
  }));
}

function eventCell(item) {
  const cell = element("td");
  if (item.event) {
    const magnitude = Number.isFinite(item.event.magnitude) ? item.event.magnitude.toFixed(1) : "—";
    cell.append(element("strong", "", `M ${magnitude} · ${placeName(item.event.place)}`));
    cell.append(element("small", "", `${dateTime(item.event.origin_time)} · ${item.event.agency || "Catálogo oficial"}`));
  } else {
    cell.append(element("span", "muted", item.report.earthquake_event_id ? "Fuera del catálogo reciente" : "Sin sismo indicado"));
    if (item.report.earthquake_event_id) cell.append(element("small", "", item.report.earthquake_event_id));
  }
  return cell;
}
function placeCell(item) {
  const cell = element("td");
  cell.append(element("strong", "", country(item.report.country_code)));
  const {latitude, longitude} = item.report;
  if (Number.isFinite(latitude) && Number.isFinite(longitude)) {
    const link = element("a", "", `≈ ${latitude.toFixed(1)}, ${longitude.toFixed(1)} ↗`);
    link.href = `https://www.google.com/maps/search/?api=1&query=${latitude},${longitude}`;
    link.target = "_blank"; link.rel = "noopener noreferrer";
    cell.append(link);
  }
  const distance = item.plausibility.distance_km;
  if (Number.isFinite(distance)) cell.append(element("small", "", `a ${Math.round(distance).toLocaleString("es")} km del epicentro`));
  return cell;
}
function experienceCell(item) {
  const cell = element("td");
  const report = item.report;
  if (item.kind === "damage") {
    cell.append(element("strong", "", `Daños: ${SEVERITY[report.severity] || report.severity || "—"}`));
    const alerts = [report.people_trapped && "personas atrapadas", report.injuries_observed && "heridos"].filter(Boolean);
    if (alerts.length) cell.append(element("small", "danger-text", alerts.join(" · ")));
  } else if (report.felt) {
    const mmi = ROMAN[report.intensity_mmi] || report.intensity_mmi || "—";
    cell.append(element("strong", "", `Lo sintió · ${mmi}`));
    if (Number.isFinite(item.plausibility.expected_mmi)) cell.append(element("small", "", `esperada ~${ROMAN[Math.max(1, Math.min(10, Math.round(item.plausibility.expected_mmi)))]}`));
  } else {
    cell.append(element("strong", "", "No lo sintió"));
  }
  return cell;
}
function plausibilityCell(item) {
  const cell = element("td");
  const status = item.plausibility.status;
  cell.append(element("span", `badge ${status}`, PLAUSIBILITY[status] || status));
  for (const reason of item.plausibility.reasons) cell.append(element("small", "", reason));
  return cell;
}
function reviewCell(item) {
  const cell = element("td", "review-cell");
  const status = reviewStatus(item);
  cell.append(element("span", `badge review-${status}`, REVIEW[status] || "Sin revisar"));
  if (item.review) cell.append(element("small", "", `${item.review.by} · ${dateTime(item.review.at)}`));
  const actions = element("div", "review-actions");
  for (const [value, label] of [["valid", "Válido"], ["dismissed", "Descartar"], ["pending", "Deshacer"]]) {
    if (value === status) continue;
    const button = element("button", value === "dismissed" ? "danger" : "", label);
    button.type = "button";
    button.addEventListener("click", () => setReview(item, value, button));
    actions.append(button);
  }
  const details = element("button", "link-button", "Detalles");
  details.type = "button";
  details.setAttribute("aria-expanded", "false");
  details.addEventListener("click", () => toggleDetails(details, item));
  actions.append(details);
  cell.append(actions);
  return cell;
}
function toggleDetails(button, item) {
  const row = button.closest("tr");
  const open = row.nextElementSibling?.classList.contains("detail-row");
  if (open) { row.nextElementSibling.remove(); button.setAttribute("aria-expanded", "false"); return; }
  const detail = element("tr", "detail-row");
  const cell = element("td");
  cell.colSpan = 7;
  const list = element("dl");
  for (const [key, value] of Object.entries(item.report)) {
    if (value === null || value === "" || (Array.isArray(value) && !value.length)) continue;
    list.append(element("dt", "", key), element("dd", "", typeof value === "object" ? JSON.stringify(value) : String(value)));
  }
  list.append(element("dt", "", "stream"), element("dd", "", item.id));
  cell.append(list);
  detail.append(cell);
  row.after(detail);
  button.setAttribute("aria-expanded", "true");
}
function render() {
  renderStats();
  const visible = reports.filter(matches);
  $("#count").textContent = `${visible.length} de ${reports.length} reportes`;
  $("#rows").replaceChildren(...visible.map(item => {
    const row = element("tr", reviewStatus(item) === "dismissed" ? "dismissed" : "");
    const received = element("td");
    received.append(element("strong", "", dateTime(item.received_at)), element("small", "", ago(item.received_at)));
    const origin = element("td");
    origin.append(element("span", `badge source-${item.source}`, item.source === "web" ? "ifeltit" : "App"));
    if (item.kind === "damage") origin.append(element("small", "", "Reporte de daños"));
    row.append(received, origin, eventCell(item), placeCell(item), experienceCell(item), plausibilityCell(item), reviewCell(item));
    return row;
  }));
  if (!visible.length) {
    const empty = element("tr");
    const cell = element("td", "empty", reports.length ? "Ningún reporte coincide con los filtros." : "Todavía no hay reportes.");
    cell.colSpan = 7;
    empty.append(cell);
    $("#rows").append(empty);
  }
}

async function setReview(item, status, button) {
  button.disabled = true;
  const stream = item.kind === "damage" ? "damage" : "felt";
  try {
    const approval = await approveAction(`review:${stream}:${item.stream_id}:${status}`, `Marcar reporte ${item.stream_id}: ${status}`);
    if (!approval) { button.disabled = false; return; }
    const result = await api(`/v1/reports/admin/reports/${stream}/${encodeURIComponent(item.stream_id)}/review`, {
      method:"POST", approval, body:JSON.stringify({status}),
    });
    item.review = result.review;
    render();
  } catch (error) {
    button.disabled = false;
    $("#reports-status").textContent = `No se guardó la revisión: ${error.message}`;
  }
}

function exportCsv() {
  const columns = ["recibido", "origen", "tipo", "sismo", "magnitud", "pais", "latitud", "longitud", "distancia_km", "sintio", "intensidad", "plausibilidad", "motivos", "revision", "report_id"];
  const quote = value => {
    let text = String(value ?? "");
    if (typeof value === "string" && /^[\s\u0000-\u001f]*[=+@-]/u.test(text)) text = "'" + text;
    return `"${text.replaceAll('"', '""')}"`;
  };
  const lines = reports.filter(matches).map(item => [
    item.received_at, item.source === "web" ? "ifeltit" : "app", item.kind, item.event?.place || item.report.earthquake_event_id,
    item.event?.magnitude, item.report.country_code, item.report.latitude, item.report.longitude, item.plausibility.distance_km,
    item.report.felt, item.report.intensity_mmi, item.plausibility.status, item.plausibility.reasons.join("; "), reviewStatus(item), item.report.report_id,
  ].map(quote).join(","));
  const blob = new Blob([[columns.join(","), ...lines].join("\n")], {type:"text/csv;charset=utf-8"});
  const link = element("a");
  link.href = URL.createObjectURL(blob);
  link.download = `seismik-reportes-${new Date().toISOString().slice(0, 10)}.csv`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}

$("#reload").addEventListener("click", loadReports);
$("#export").addEventListener("click", exportCsv);
$("#filters").addEventListener("input", render);
$("#filters").addEventListener("submit", event => event.preventDefault());
