"use strict";
const form = document.querySelector("#report-form");
const status = document.querySelector("#status");
const steps = [...form.querySelectorAll("[data-step]")];
const control = (name) => form.elements.namedItem(name);
let step = 0, config, widget, token = "", pending, busy = false, accuracy = null;
let events = [], map, youMarker, quakeMarker, quakeRing, geocoder, catalogRequest = 0, mapLoading = false;
const requestedEvent = new URLSearchParams(window.location?.search || "").get("event");
// Si una agencia regional publicó el sismo, su ID abre los formularios oficiales del país.
const GLOBAL_SOURCES = /^(emsc|usgs)/;
const NEARBY_KM = 1000;
const magnitudeText = value => Number.isFinite(value) ? value.toFixed(1) : "—";
const scriptNonce = document.querySelector("script[nonce]")?.nonce || "";
const localDate = value => new Date(value).toLocaleString("es", {dateStyle:"medium", timeStyle:"short"});
const toLocalInput = date => new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0,16);
const kmText = km => km < 10 ? `${km.toFixed(1)} km` : `${Math.round(km).toLocaleString("es")} km`;
const hasPoint = event => Number.isFinite(event?.latitude) && Number.isFinite(event?.longitude);
control("observed_at").value = toLocalInput(new Date());

// Algunas agencias publican el lugar en mayúsculas; se muestra como nombre propio.
function placeName(event) {
  const place = (event?.place || "").trim();
  if (!place) return "Ubicación sin descripción";
  if (place !== place.toUpperCase()) return place;
  return place.toLocaleLowerCase("es").replace(/(^|[\s,(/-])(\p{L})/gu, (_, gap, letter) => gap + letter.toLocaleUpperCase("es"));
}
function distanceKm(a, b) {
  const rad = Math.PI / 180, dLat = (b.latitude - a.latitude) * rad, dLon = (b.longitude - a.longitude) * rad;
  const h = Math.sin(dLat/2)**2 + Math.cos(a.latitude*rad) * Math.cos(b.latitude*rad) * Math.sin(dLon/2)**2;
  return 12742 * Math.asin(Math.min(1, Math.sqrt(h)));
}
// Radio aproximado en el que una persona suele notar un sismo de esta magnitud.
// Es orientativo: sólo decide si mostramos un aviso, nunca bloquea el envío.
const feltRadiusKm = magnitude => 10 ** (0.42 * magnitude + 0.2);
const reporter = () => {
  const latitude = Number(control("latitude").value), longitude = Number(control("longitude").value);
  return control("latitude").value && control("longitude").value ? {latitude, longitude} : null;
};
// Preguntas ocultas dentro de su paso (p. ej. detalles cuando no se sintió).
// Se detiene en el fieldset: el paso entero está oculto mientras no se muestra.
function concealed(element) {
  for (let node = element.parentElement; node && node.tagName !== "FIELDSET"; node = node.parentElement) if (node.hidden) return true;
  return false;
}
const selectedEvent = () =>events.find(event => event.event_id === control("earthquake_event_id").value);
const relative = new Intl.RelativeTimeFormat("es", {numeric:"auto"});
function ago(value) {
  const minutes = Math.round((new Date(value) - Date.now()) / 60000);
  if (Math.abs(minutes) < 60) return relative.format(minutes, "minute");
  if (Math.abs(minutes) < 1440) return relative.format(Math.round(minutes / 60), "hour");
  return relative.format(Math.round(minutes / 1440), "day");
}

function payload() {
  const data = new FormData(form);
  const felt = data.get("felt") === "true";
  const report = {
    earthquake_event_id: data.get("earthquake_event_id"),
    observed_at: new Date(data.get("observed_at")).toISOString(),
    country_code: data.get("country_code").toUpperCase(),
    latitude: Number(data.get("latitude")), longitude: Number(data.get("longitude")),
    location_precision: control("precise").checked ? "precise" : "approximate",
    location_accuracy_m: accuracy,
    felt,
    intensity_mmi: felt ? Number(data.get("intensity_mmi")) : null,
    share_with_official_agencies: control("share_with_official_agencies").checked,
  };
  // Quien no lo sintió no describe cómo se sintió.
  if (!felt) return report;
  for (const name of ["duration_seconds", "building_height", "floor"]) {
    if (data.get(name) !== "" && !concealed(control(name))) report[name] = Number(data.get(name));
  }
  for (const name of ["movement", "activity", "building_type", "reaction", "others_felt", "noise", "windows", "lamps", "furniture"]) {
    if (data.get(name)) report[name] = data.get(name);
  }
  return report;
}
function addSummary(summary, term, value) {
  const dt = document.createElement("dt"), dd = document.createElement("dd");
  dt.textContent = term; dd.textContent = value; summary.append(dt, dd);
}
function review() {
  const summary = document.querySelector("#summary");
  summary.replaceChildren();
  const selected = selectedEvent(), here = reporter();
  if (selected) addSummary(summary, "Sismo", `M ${magnitudeText(selected.magnitude)} · ${placeName(selected)} · ${localDate(selected.origin_time)}`);
  if (selected && here && hasPoint(selected)) addSummary(summary, "Distancia al epicentro", kmText(distanceKm(here, selected)));
  for (const element of form.querySelectorAll("input, select")) {
    if (!element.name || element.name === "earthquake_event_id" || ["checkbox", "hidden"].includes(element.type) || !element.value) continue;
    if (concealed(element)) continue;
    addSummary(summary, element.closest("label").firstChild.textContent.trim(),
      element.tagName === "SELECT" ? element.selectedOptions[0].textContent
        : element.type === "datetime-local" ? localDate(element.value) : element.value);
  }
  addSummary(summary, "Ubicación almacenada", control("precise").checked ? "Exacta, por tu elección" : "Punto elegido en el mapa, redondeado a unos 1 km");
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
  if (index === 0 && !reporter()) {
    status.textContent = "Elige dónde estabas tocando el mapa o usando tu ubicación.";
    document.querySelector("#location-status").textContent = "Selecciona una ubicación antes de continuar.";
    return false;
  }
  for (const el of steps[index].querySelectorAll("input,select")) {
    if (concealed(el)) continue;
    if (!el.checkValidity()) { el.reportValidity(); return false; }
  }
  return true;
}
function syncExperience() {
  const answer = control("felt").value;
  const felt = answer === "true";
  document.querySelector("#intensity-label").hidden = !felt;
  document.querySelector("#felt-details").hidden = !felt;
  document.querySelector("#not-felt-note").hidden = answer !== "false";
  control("intensity_mmi").required = felt;
  if (!felt) control("intensity_mmi").value = "";
  // Al aire libre no hay pisos que contar.
  const outside = control("building_type").value === "outside";
  for (const label of document.querySelectorAll(".building-only")) label.hidden = outside;
}
form.addEventListener("input", (event) => {
  if (event.target.name) pending = undefined;
  syncExperience();
});
document.querySelector("#next").addEventListener("click", () => { if (valid(step)) showStep(step+1); });
document.querySelector("#back").addEventListener("click", () => showStep(step-1));

// Dibuja al visitante y al epicentro, y encuadra ambos para que la distancia se vea.
function drawMap(focus) {
  if (!map) return;
  const maps = window.google.maps, here = reporter(), quake = selectedEvent();
  if (here) {
    const point = {lat:here.latitude, lng:here.longitude};
    if (!youMarker) {
      youMarker = new maps.Marker({map, draggable:true, title:"Tu ubicación", zIndex:2, icon:{
        path:maps.SymbolPath.CIRCLE, scale:9, fillColor:"#2678ed", fillOpacity:1, strokeColor:"#ffffff", strokeWeight:3,
      }});
      youMarker.addListener?.("dragend", event => { if (event.latLng) chooseLocation(event.latLng.lat(), event.latLng.lng()); });
    }
    youMarker.setPosition(point);
  }
  if (hasPoint(quake)) {
    const point = {lat:quake.latitude, lng:quake.longitude};
    if (!quakeMarker) quakeMarker = new maps.Marker({map, clickable:false, zIndex:1, icon:{
      path:maps.SymbolPath.CIRCLE, scale:7, fillColor:"#ff5a3c", fillOpacity:1, strokeColor:"#ffffff", strokeWeight:2,
    }});
    quakeMarker.setPosition(point); quakeMarker.setMap?.(map);
    quakeMarker.setTitle?.(`Epicentro · M ${magnitudeText(quake.magnitude)} · ${placeName(quake)}`);
    // Zona donde suele sentirse: da una idea de escala, no es un mapa de intensidad.
    if (!quakeRing) quakeRing = new maps.Circle({map, clickable:false, strokeColor:"#ff5a3c", strokeOpacity:0.6, strokeWeight:1, fillColor:"#ff5a3c", fillOpacity:0.08});
    quakeRing.setCenter(point); quakeRing.setRadius?.(feltRadiusKm(quake.magnitude || 0) * 1000); quakeRing.setMap?.(map);
  } else {
    quakeMarker?.setMap?.(null); quakeRing?.setMap?.(null);
  }
  if (!focus) return;
  if (here && hasPoint(quake) && maps.LatLngBounds) {
    const bounds = new maps.LatLngBounds();
    bounds.extend({lat:here.latitude, lng:here.longitude}); bounds.extend({lat:quake.latitude, lng:quake.longitude});
    map.fitBounds(bounds, 60);
    if (distanceKm(here, quake) < 5) map.setZoom(11);
  } else if (here) {
    map.panTo({lat:here.latitude, lng:here.longitude}); map.setZoom(Math.max(map.getZoom?.() || 0, 10));
  } else if (hasPoint(quake)) {
    map.panTo({lat:quake.latitude, lng:quake.longitude}); map.setZoom(6);
  }
}
function updatePlausibility() {
  const note = document.querySelector("#plausibility"), distance = document.querySelector("#event-distance");
  const here = reporter(), quake = selectedEvent();
  note.hidden = true; distance.textContent = "";
  if (!here || !hasPoint(quake)) return;
  const km = distanceKm(here, quake);
  distance.textContent = `Estabas a ${kmText(km)} del epicentro.`;
  if (Number.isFinite(quake.magnitude) && km > 2 * feltRadiusKm(quake.magnitude)) {
    note.textContent = `Un sismo de magnitud ${magnitudeText(quake.magnitude)} rara vez se siente a ${kmText(km)}. Revisa que el sismo y tu ubicación sean correctos; si lo son, puedes continuar.`;
    note.hidden = false;
  }
}
function guessCountry(latitude, longitude) {
  const maps = window.google?.maps;
  if (!maps?.Geocoder) return;
  // Sin Geocoding API habilitada (o si Maps falla) el país se elige a mano.
  Promise.resolve().then(() => (geocoder ||= new maps.Geocoder()).geocode({location:{lat:latitude, lng:longitude}})).then(({results} = {}) => {
    // Si el visitante movió el punto mientras tanto, esta respuesta ya no vale.
    if (Number(control("latitude").value) !== latitude || Number(control("longitude").value) !== longitude) return;
    const code = results?.flatMap(result => result.address_components).find(part => part.types.includes("country"))?.short_name;
    const picker = control("country_code");
    if (code && [...picker.options].some(option => option.value === code) && picker.value !== code) {
      picker.value = code; pending = undefined;
      document.querySelector("#country-hint").textContent = "Deducido del punto del mapa. Corrígelo si no coincide.";
    }
  }).catch(() => {});
}
function chooseLocation(latitude, longitude, gpsAccuracy = null) {
  if (busy || !Number.isFinite(latitude) || !Number.isFinite(longitude)) return;
  const first = !reporter();
  control("latitude").value = latitude; control("longitude").value = longitude;
  if (accuracy !== gpsAccuracy || pending?.report.latitude !== latitude || pending?.report.longitude !== longitude) pending = undefined;
  accuracy = gpsAccuracy;
  drawMap(first || gpsAccuracy !== null);
  guessCountry(latitude, longitude);
  document.querySelector("#location-status").textContent = gpsAccuracy !== null
    ? `Ubicación del dispositivo (precisión de unos ${Math.round(gpsAccuracy)} m). Arrastra el punto si no es exacta.`
    : "Ubicación elegida. Arrastra el punto o toca otra parte del mapa para moverlo.";
  renderEvents(); updatePlausibility();
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
  // Maps busca su nonce de estilos con `style[nonce]`: hace falta el atributo,
  // no sólo la propiedad. Sin él, la CSP bloquea su CSS y cada botón del mapa
  // muestra a la vez sus imágenes normal, hover y activa.
  const mapsStyle = document.createElement("style"); mapsStyle.setAttribute("nonce", scriptNonce); document.head.append(mapsStyle);
  window.initFeltMap = () => {
    // Sin restricción, al alejar Google repite el planeta en horizontal y deja
    // franjas grises sobre los polos. La vista inicial usa la zona horaria del
    // dispositivo para empezar cerca del visitante, sin pedir permisos.
    const longitude = Math.max(-170, Math.min(170, -new Date().getTimezoneOffset() / 4));
    map = new window.google.maps.Map(document.querySelector("#location-map"), {
      center:{lat:10, lng:longitude}, zoom:3, minZoom:2, mapTypeControl:false,
      streetViewControl:false, fullscreenControl:true, gestureHandling:"cooperative",
      restriction:{latLngBounds:{north:85, south:-85, west:-180, east:180}, strictBounds:true},
    });
    map.addListener("click", event => { if (event.latLng) chooseLocation(event.latLng.lat(), event.latLng.lng()); });
    message.hidden = true; document.querySelector("#choose-center").disabled = false;
    drawMap(true);
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

// Varias agencias publican el mismo sismo con IDs propios. Se agrupan las
// versiones con menos de 90 s y 150 km de diferencia y se conserva una sola.
function mergeDuplicates(list) {
  const merged = [];
  for (const event of list) {
    const twin = merged.find(other => Math.abs(new Date(other.origin_time) - new Date(event.origin_time)) < 90000
      && (!hasPoint(other) || !hasPoint(event) || distanceKm(other, event) < 150));
    if (!twin) { merged.push({...event, agencies:[event.agency].filter(Boolean)}); continue; }
    if (event.agency && !twin.agencies.includes(event.agency)) twin.agencies.push(event.agency);
    if (GLOBAL_SOURCES.test(twin.source_id || "") && !GLOBAL_SOURCES.test(event.source_id || "")) {
      Object.assign(twin, {...event, agencies:twin.agencies, place: event.place || twin.place});
    }
  }
  return merged;
}
function eventOption(event, here) {
  const option = document.createElement("option"); option.value = event.event_id;
  const away = here && hasPoint(event) ? ` · a ${kmText(distanceKm(here, event))}` : "";
  option.textContent = `M ${magnitudeText(event.magnitude)} · ${placeName(event)} · ${ago(event.origin_time)}${away}`;
  return option;
}
function renderEvents() {
  const picker = control("earthquake_event_id"), selected = picker.value, here = reporter();
  const query = document.querySelector("#event-search").value.trim().toLocaleLowerCase("es");
  picker.replaceChildren();
  const placeholder = document.createElement("option"); placeholder.value = "";
  placeholder.textContent = events.length ? "Selecciona el sismo" : "No hay sismos en el catálogo"; picker.append(placeholder);
  const matches = events.filter(event => !query || event.event_id === selected
    || [event.place, placeName(event), ...(event.agencies || [])].some(text => (text || "").toLocaleLowerCase("es").includes(query)));
  const nearby = here ? matches.filter(event => hasPoint(event) && distanceKm(here, event) <= NEARBY_KM) : [];
  if (nearby.length) {
    // Cerca primero: es lo que con más probabilidad sentiste.
    const close = document.createElement("optgroup"); close.label = `Cerca de ti (menos de ${NEARBY_KM.toLocaleString("es")} km)`;
    const rest = document.createElement("optgroup"); rest.label = "Otros sismos recientes";
    for (const event of matches) (nearby.includes(event) ? close : rest).append(eventOption(event, here));
    picker.append(close); if (matches.length > nearby.length) picker.append(rest);
  } else for (const event of matches) picker.append(eventOption(event, here));
  picker.value = events.some(event => event.event_id === selected) ? selected : "";
  const message = document.querySelector("#event-status");
  if (!matches.length) message.textContent = "No hay sismos que coincidan. Prueba con otro lugar.";
  else if (here) message.textContent = nearby.length
    ? `${nearby.length} de ${matches.length} sismos ocurrieron a menos de ${NEARBY_KM.toLocaleString("es")} km de ti.`
    : `Ninguno de los ${matches.length} sismos ocurrió a menos de ${NEARBY_KM.toLocaleString("es")} km de ti. Revisa tu ubicación o busca por lugar.`;
  else message.textContent = `${matches.length} sismos en el catálogo. Marca tu ubicación para ver primero los cercanos.`;
}
function selectEvent() {
  if (busy) return;
  const selected = selectedEvent();
  document.querySelector("#selected-event").hidden = !selected;
  pending = undefined;
  drawMap(true); updatePlausibility();
  if (!selected) return;
  document.querySelector("#event-magnitude").textContent = `M ${magnitudeText(selected.magnitude)}`;
  document.querySelector("#event-place").textContent = placeName(selected);
  const depth = Number.isFinite(selected.depth_km) ? ` · ${Math.round(selected.depth_km)} km de profundidad` : "";
  document.querySelector("#event-time").textContent = `${localDate(selected.origin_time)} (${ago(selected.origin_time)})${depth}`;
  document.querySelector("#event-agency").textContent = (selected.agencies?.length ? selected.agencies : [selected.agency || "Catálogo oficial"]).join(" · ");
  control("observed_at").value = toLocalInput(new Date(selected.origin_time));
}
async function loadEvents() {
  const message = document.querySelector("#event-status");
  const request = ++catalogRequest;
  message.textContent = "Consultando sismos recientes…";
  try {
    const response = await fetch("/v1/reports/web/events", {cache:"no-store", signal:AbortSignal.timeout(10000)});
    if (!response.ok) throw new Error("No se pudo consultar el catálogo. Pulsa Actualizar catálogo para reintentar.");
    const result = await response.json();
    if (!Array.isArray(result.events)) throw new Error("El catálogo no está disponible. Reintenta más tarde.");
    if (busy || request !== catalogRequest) return;
    const saved = selectedEvent();
    events = mergeDuplicates(result.events);
    if (saved && !events.some(event => event.event_id === saved.event_id)) events.push(saved);
    const selected = control("earthquake_event_id").value;
    renderEvents();
    if (requestedEvent && !selected) {
      // Enlace desde seismik.org: el sismo llega elegido si sigue en el catálogo.
      // El ID puede ser de una versión que se fusionó con otra agencia.
      const raw = result.events.find(event => event.event_id === requestedEvent);
      const match = raw && events.find(event => event.event_id === raw.event_id || mergeDuplicates([event, raw]).length === 1);
      if (match) { control("earthquake_event_id").value = match.event_id; selectEvent(); }
      else message.textContent = "El sismo del enlace ya no está en el catálogo de los últimos 7 días. Elige otro de la lista.";
    }
    if (selected && !control("earthquake_event_id").value) { pending = undefined; document.querySelector("#selected-event").hidden = true; }
  } catch (error) { if (request === catalogRequest) message.textContent = error.message; }
}
const countryNames = new Intl.DisplayNames(["es"], {type:"region"});
const countries = "AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW".split(" ");
for (const code of countries.sort((a,b) => countryNames.of(a).localeCompare(countryNames.of(b), "es"))) {
  const option = document.createElement("option"); option.value = code; option.textContent = countryNames.of(code); control("country_code").append(option);
}
const unknownCountry = document.createElement("option"); unknownCountry.value = "ZZ"; unknownCountry.textContent = "Otro / no sé"; control("country_code").append(unknownCountry);
// El catálogo ya está en el navegador: filtrar no consume el límite de consultas.
document.querySelector("#event-search").addEventListener("input", renderEvents);
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
