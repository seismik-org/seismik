"use strict";
const form = document.querySelector("#report-form");
const status = document.querySelector("#status");
const steps = [...form.querySelectorAll("[data-step]")];
const control = (name) => form.elements.namedItem(name);
let step = 0, config, widget, token = "", pending, busy = false, accuracy = null;
let events = [], map, locationCircle, mapLoading = false, searchTimer, catalogRequest = 0;
const magnitudeText = value => Number.isFinite(value) ? value.toFixed(1) : "—";
const scriptNonce = document.querySelector("script[nonce]")?.nonce || "";
const localDate = value => new Date(value).toLocaleString("es", {dateStyle:"medium", timeStyle:"short"});
const now = new Date();
control("observed_at").value = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0,16);

function payload() {
  const data = new FormData(form);
  const report = {
    earthquake_event_id: data.get("earthquake_event_id"),
    observed_at: new Date(data.get("observed_at")).toISOString(),
    country_code: data.get("country_code").toUpperCase(),
    latitude: Number(data.get("latitude")), longitude: Number(data.get("longitude")),
    location_precision: control("precise").checked ? "precise" : "approximate",
    location_accuracy_m: accuracy,
    felt: data.get("felt") === "true",
    intensity_mmi: data.get("felt") === "true" ? Number(data.get("intensity_mmi")) : null,
    share_with_official_agencies: control("share_with_official_agencies").checked,
  };
  for (const name of ["duration_seconds", "building_height", "floor"]) {
    if (data.get(name) !== "") report[name] = Number(data.get(name));
  }
  for (const name of ["movement", "activity", "building_type", "reaction", "others_felt", "noise", "windows", "lamps", "furniture"]) {
    if (data.get(name)) report[name] = data.get(name);
  }
  return report;
}
function review() {
  const summary = document.querySelector("#summary");
  summary.replaceChildren();
  for (const element of form.querySelectorAll("input, select")) {
    if (!element.name || ["checkbox", "hidden"].includes(element.type) || !element.value || element.closest("#intensity-label")?.hidden) continue;
    const dt = document.createElement("dt"), dd = document.createElement("dd");
    dt.textContent = element.closest("label").firstChild.textContent.trim();
    dd.textContent = element.tagName === "SELECT" ? element.selectedOptions[0].textContent : element.value;
    summary.append(dt,dd);
  }
  const dt = document.createElement("dt"), dd = document.createElement("dd");
  dt.textContent = "Ubicación almacenada";
  dd.textContent = control("precise").checked ? "Exacta, por tu elección" : "Punto elegido en Google Maps · aproximada";
  summary.append(dt,dd);
}
function showStep(index) {
  step = index;
  status.textContent = "";
  steps.forEach((el,i) => el.hidden = i !== step);
  document.querySelectorAll(".steps li").forEach((el,i) => {
    if (i === step) el.setAttribute("aria-current","step"); else el.removeAttribute("aria-current");
  });
  document.querySelector("#back").hidden = step === 0;
  document.querySelector("#next").hidden = step === 2;
  document.querySelector("#send").hidden = step !== 2;
  steps[step].scrollIntoView?.({block:"start"});
  steps[step].querySelector("legend")?.focus?.();
  if (step === 2) { review(); loadConfig().catch(error => { status.textContent = error.message; }); }
}
function valid(index) {
  if (index === 0 && (!control("latitude").value || !control("longitude").value)) {
    status.textContent = "Elige dónde estabas tocando el mapa o usando tu ubicación.";
    document.querySelector("#location-status").textContent = "Selecciona una ubicación antes de continuar.";
    return false;
  }
  for (const el of steps[index].querySelectorAll("input,select")) {
    if (!el.checkValidity()) { el.reportValidity(); return false; }
  }
  return true;
}
form.addEventListener("input", (event) => {
  if (event.target.name) pending = undefined;
  const felt = control("felt").value === "true";
  document.querySelector("#intensity-label").hidden = !felt;
  control("intensity_mmi").required = felt;
  if (!felt) control("intensity_mmi").value = "";
});
document.querySelector("#next").addEventListener("click", () => { if (valid(step)) showStep(step+1); });
document.querySelector("#back").addEventListener("click", () => showStep(step-1));

function chooseLocation(latitude, longitude, gpsAccuracy = null) {
  if (busy || !Number.isFinite(latitude) || !Number.isFinite(longitude)) return;
  control("latitude").value = latitude; control("longitude").value = longitude;
  if (accuracy !== gpsAccuracy || pending?.report.latitude !== latitude || pending?.report.longitude !== longitude) pending = undefined;
  accuracy = gpsAccuracy;
  if (map) {
    const point = {lat:latitude, lng:longitude};
    map.panTo(point); map.setZoom(15);
    if (!locationCircle) locationCircle = new window.google.maps.Circle({
      map, radius:35, strokeColor:"#ffffff", strokeWeight:3,
      fillColor:"#2678ed", fillOpacity:0.85, clickable:false,
    });
    locationCircle.setCenter(point);
  }
  document.querySelector("#location-status").textContent = "Ubicación elegida. Puedes mover el punto tocando otra parte del mapa.";
  if (step === 2) review();
}
document.querySelector("#locate").addEventListener("click", () => {
  const message = document.querySelector("#location-status");
  if (!navigator.geolocation) { message.textContent = "Geolocalización no disponible. Elige un punto en el mapa."; return; }
  message.textContent = "Buscando ubicación…";
  navigator.geolocation.getCurrentPosition(({coords}) => {
    chooseLocation(coords.latitude, coords.longitude, coords.accuracy);
  }, () => { message.textContent = "No pudimos obtener tu ubicación. Elige un punto en el mapa."; }, {timeout:10000, maximumAge:60000});
});
document.querySelector("#choose-center").addEventListener("click", () => {
  const center = map?.getCenter();
  if (center) chooseLocation(center.lat(), center.lng());
});
function loadMap(key) {
  const message = document.querySelector("#map-message");
  if (!key) {
    message.querySelector("p").textContent = "El mapa todavía no está configurado. Puedes usar la ubicación de tu dispositivo.";
    return;
  }
  if (mapLoading) return;
  mapLoading = true;
  const mapsStyle = document.createElement("style"); mapsStyle.nonce = scriptNonce; document.head.append(mapsStyle);
  window.initFeltMap = () => {
    map = new window.google.maps.Map(document.querySelector("#location-map"), {
      center:{lat:4.65, lng:-74.05}, zoom:5, mapTypeControl:false,
      streetViewControl:false, fullscreenControl:true, gestureHandling:"cooperative",
    });
    map.addListener("click", event => { if (event.latLng) chooseLocation(event.latLng.lat(), event.latLng.lng()); });
    message.hidden = true; document.querySelector("#choose-center").disabled = false;
    if (control("latitude").value && control("longitude").value) {
      const savedAccuracy = accuracy;
      chooseLocation(Number(control("latitude").value), Number(control("longitude").value), savedAccuracy);
    }
  };
  window.gm_authFailure = () => {
    message.hidden = false;
    message.querySelector("p").textContent = "Google Maps no pudo verificar su configuración. Usa tu ubicación o vuelve a intentarlo más tarde.";
  };
  const script = document.createElement("script"); script.nonce = scriptNonce;
  const url = new URL("https://maps.googleapis.com/maps/api/js");
  url.search = new URLSearchParams({key, callback:"initFeltMap", loading:"async", v:"weekly", language:"es"}).toString();
  script.src = url.href; script.async = true;
  script.onerror = () => { mapLoading = false; script.remove(); message.querySelector("p").textContent = "No se pudo cargar Google Maps. Usa tu ubicación o reintenta la conexión."; };
  document.head.append(script);
}
function renderEvents() {
  const picker = control("earthquake_event_id"), selected = picker.value;
  const query = document.querySelector("#event-search").value.toLocaleLowerCase("es");
  picker.replaceChildren();
  const placeholder = document.createElement("option"); placeholder.value = ""; placeholder.textContent = "Selecciona el sismo"; picker.append(placeholder);
  const matches = events.filter(event => !query || (event.place || "").toLocaleLowerCase("es").includes(query) || event.event_id === selected);
  for (const event of matches) {
    const option = document.createElement("option"); option.value = event.event_id;
    option.textContent = `M ${magnitudeText(event.magnitude)} · ${event.place || "Ubicación sin descripción"} · ${localDate(event.origin_time)}`;
    picker.append(option);
  }
  picker.value = events.some(event => event.event_id === selected) ? selected : "";
  document.querySelector("#event-status").textContent = matches.length ? `${matches.length} sismos disponibles. Si no aparece el que buscas, actualiza el catálogo más tarde.` : "No hay sismos que coincidan. Prueba con otro lugar.";
}
function selectEvent() {
  if (busy) return;
  const selected = events.find(event => event.event_id === control("earthquake_event_id").value);
  document.querySelector("#selected-event").hidden = !selected;
  pending = undefined;
  if (!selected) return;
  document.querySelector("#event-magnitude").textContent = `M ${magnitudeText(selected.magnitude)}`;
  document.querySelector("#event-place").textContent = selected.place || "Ubicación sin descripción";
  document.querySelector("#event-time").textContent = localDate(selected.origin_time);
  document.querySelector("#event-agency").textContent = selected.agency || "Catálogo oficial";
  const date = new Date(selected.origin_time);
  control("observed_at").value = new Date(date.getTime() - date.getTimezoneOffset()*60000).toISOString().slice(0,16);
  // The epicenter helps orient the map; it never selects the visitor's location.
  if (map && !control("latitude").value && Number.isFinite(selected.latitude) && Number.isFinite(selected.longitude)) {
    map.panTo({lat:selected.latitude, lng:selected.longitude}); map.setZoom(6);
  }
}
async function loadEvents() {
  const message = document.querySelector("#event-status");
  const request = ++catalogRequest;
  message.textContent = "Consultando sismos recientes…";
  try {
    const query = document.querySelector("#event-search").value.trim();
    const response = await fetch("/v1/reports/web/events" + (query ? `?q=${encodeURIComponent(query)}` : ""), {cache:"no-store", signal:AbortSignal.timeout(10000)});
    if (!response.ok) throw new Error("No se pudo consultar el catálogo. Pulsa Actualizar catálogo para reintentar.");
    const result = await response.json();
    if (!Array.isArray(result.events)) throw new Error("El catálogo no está disponible. Reintenta más tarde.");
    if (busy || request !== catalogRequest) return;
    const saved = events.find(event => event.event_id === control("earthquake_event_id").value);
    events = result.events;
    if (saved && !events.some(event => event.event_id === saved.event_id)) events.push(saved);
    const selected = control("earthquake_event_id").value;
    renderEvents();
    if (selected && !control("earthquake_event_id").value) { pending = undefined; document.querySelector("#selected-event").hidden = true; }
  } catch (error) { if (request === catalogRequest) message.textContent = error.message; }
}
const countryNames = new Intl.DisplayNames(["es"], {type:"region"});
const countries = "AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW".split(" ");
for (const code of countries.sort((a,b) => countryNames.of(a).localeCompare(countryNames.of(b), "es"))) {
  const option = document.createElement("option"); option.value = code; option.textContent = countryNames.of(code); control("country_code").append(option);
}
const unknownCountry = document.createElement("option"); unknownCountry.value = "ZZ"; unknownCountry.textContent = "Otro / no sé"; control("country_code").append(unknownCountry);
document.querySelector("#event-search").addEventListener("input", () => {
  clearTimeout(searchTimer); searchTimer = setTimeout(loadEvents, 500);
});
control("earthquake_event_id").addEventListener("change", selectEvent);
document.querySelector("#reload-events").addEventListener("click", loadEvents);
async function loadConfig() {
  const response = await fetch("/v1/reports/web/config", {cache:"no-store", signal:AbortSignal.timeout(10000)});
  if (!response.ok) throw new Error("No se pudo cargar la configuración. Intenta enviar de nuevo.");
  config = await response.json();
  loadMap(config.google_maps_api_key);
  if (!config.enabled) throw new Error("El envío aún no está habilitado. Inténtalo más tarde.");
  if (!config.turnstile_required || step !== 2) return;
  if (!window.turnstile) await new Promise((resolve,reject) => {
    const script = document.createElement("script");
    script.nonce = scriptNonce;
    script.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
    script.onload = resolve; script.onerror = () => { script.remove(); reject(new Error("No se pudo cargar la verificación. Inténtalo de nuevo.")); };
    document.head.append(script);
  });
  if (widget === undefined) widget = window.turnstile.render("#turnstile-container", {
    sitekey:config.site_key, action:"felt_report",
    callback: value => {token = value; status.textContent = "Verificación lista.";},
    "expired-callback": () => {token = "";},
    "error-callback": () => {token = ""; status.textContent = "Falló la verificación. Reintenta el widget antes de enviar."; return true;},
  });
}
form.addEventListener("submit", async event => {
  event.preventDefault();
  if (busy) return;
  for (let i=0;i<3;i++) if (!valid(i)) { showStep(i); return; }
  busy = true;
  try {
    if (!config?.enabled || (config.turnstile_required && widget === undefined)) await loadConfig();
    if (config.turnstile_required && !token) throw new Error("Completa la verificación de seguridad antes de enviar.");
    const answers = payload();
    const fingerprint = JSON.stringify(answers);
    if (!pending || pending.fingerprint !== fingerprint) pending = {fingerprint, report:{...answers, report_id:crypto.randomUUID()}};
    // Capture values before disabling fields; keep this snapshot after a network failure.
    steps.forEach(el => el.disabled = true);
    form.querySelectorAll("button").forEach(el => el.disabled = true);
    status.textContent = "Enviando…";
    const response = await fetch("/v1/reports/web/felt", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({...pending.report, turnstile_token:token || null}), signal:AbortSignal.timeout(15000)});
    const result = await response.json();
    if (response.status !== 202 || !(result.accepted === true || result.duplicate === true) || result.report_id !== pending.report.report_id) throw new Error(typeof result.detail === "string" ? result.detail : "No se confirmó el envío. Puedes reintentarlo.");
    document.querySelector("#receipt").textContent = `Identificador: ${result.report_id}`;
    document.querySelector("#notice").textContent = result.notice;
    const links = document.querySelector("#agency-links"); links.replaceChildren();
    for (const route of result.agency_routes || []) {
      const url = new URL(route.official_url);
      if (url.protocol !== "https:") continue;
      const link = document.createElement("a"); link.href = url.href; link.textContent = `Completar formulario · ${route.agency_name}`; link.target = "_blank"; link.rel = "noopener noreferrer"; links.append(link);
    }
    form.hidden = true; document.querySelector("#result").hidden = false;
  } catch (error) {
    status.textContent = `${error.message} Tus respuestas siguen aquí; si no las cambias, el reintento usa el mismo identificador.`;
  } finally {
    busy = false; steps.forEach(el => el.disabled = false); form.querySelectorAll("button").forEach(el => el.disabled = false);
    document.querySelector("#choose-center").disabled = !map;
    token = ""; if (widget !== undefined) window.turnstile.reset(widget);
  }
});
document.querySelector("#another").addEventListener("click", () => window.location.reload());
loadConfig().catch(error => { status.textContent = error.message; });

loadEvents();
