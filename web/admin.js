"use strict";
// admin.seismik.org. Usa los utilitarios de reportes.js, que se carga antes.
const AUTH_URL = "https://auth.seismik.org/id";
const KEY_LABELS = {
  devices:"Dispositivos registrados",
  accounts_with_devices:"Cuentas con dispositivos",
  developer_accounts:"Cuentas de desarrollador",
  api_keys:"Claves de API activas",
  webhook_owners:"Cuentas con webhooks",
  family_circles:"Círculos de familia",
  admin_sessions:"Sesiones de administración",
  web_sessions:"Sesiones web abiertas",
  app_sessions:"Sesiones de la app",
};
const loaded = new Set();
let adminEpoch = 0;
let records = [];
let recordRequest = 0;
let controlsBusy = false;
let betaPhones = [];
let betaScenarios = [];
let betaBusy = false;
let drillPoll = 0;
const picked = new Set();
const PLATFORMS = {ios:"iPhone", android:"Android"};
const DRILL_STATUS = {queued:"En cola", sent:"Enviado", dry_run:"Simulado (envío desactivado)", no_targets:"Sin destinos"};

function clearData() {
  if (typeof clearMfa === "function") clearMfa();
  adminEpoch++;
  recordRequest++;
  loaded.clear();
  reports = [];
  records = [];
  betaPhones = [];
  picked.clear();
  clearTimeout(drillPoll);
  for (const selector of ["#rows", "#record-list", "#key-stats", "#stream-rows", "#stats", "#controls-list", "#record-stream", "#beta-phones", "#drill-list", "#drill-scenario"]) $(selector).replaceChildren();
  $("#export").disabled = true;
}
function accessError(error) {
  if (error.status === 428) { clearData(); start(); return true; }
  if (![401, 403].includes(error.status)) return false;
  clearData();
  showUser("");
  showGate("Vuelve a iniciar sesión", error.message);
  return true;
}

function showGate(title, text, {login = true, switchAccount = false} = {}) {
  $("#app").hidden = true;
  $("#gate").hidden = false;
  $("#gate-title").textContent = title;
  $("#gate-text").textContent = text;
  $("#gate-login").hidden = !login;
  $("#gate-switch").hidden = !switchAccount;
}
function showUser(email) {
  $("#user-label").textContent = email || "";
  $("#user-label").hidden = !email;
  $("#logout-button").hidden = !email;
}

async function login() {
  try {
    const result = await api("/v1/admin/auth/start", {method:"POST"});
    window.location.assign(result.redirect);
  } catch (error) { showGate("Acceso no disponible", error.message); }
}
async function logout() {
  try { await api("/v1/admin/auth/logout", {method:"POST"}); }
  catch (error) { $("#status").textContent = `No se pudo cerrar la sesión: ${error.message}`; return; }
  clearData();
  start();
}

async function openTab(name) {
  for (const tab of document.querySelectorAll("[data-tab]")) tab.setAttribute("aria-selected", String(tab.dataset.tab === name));
  for (const panel of document.querySelectorAll("[role=tabpanel]")) panel.hidden = panel.id !== `tab-${name}`;
  if (loaded.has(name)) return;
  const loaders = {overview:loadOverview, reports:loadReports, records:loadRecords, controls:loadControls, beta:loadBeta};
  if (await loaders[name]()) loaded.add(name);
}

async function loadOverview() {
  const epoch = adminEpoch;
  $("#overview-status").textContent = "Cargando…";
  try {
    const data = await api("/v1/admin/overview");
    if (epoch !== adminEpoch) return false;
    $("#overview-time").textContent = `Datos de ${dateTime(data.generated_at)}. Cuentas y dispositivos se cuentan en Redis; los registros, por entradas.`;
    $("#key-stats").replaceChildren(...Object.entries(KEY_LABELS).map(([key, label]) => {
      const item = element("li", "report-stat");
      item.append(element("strong", "", (data.keys[key] ?? 0).toLocaleString("es")), element("span", "", label));
      return item;
    }));
    $("#keys-note").hidden = data.keys_complete;
    $("#keys-note").textContent = "Recuento parcial: hay demasiadas claves en Redis para contarlas todas.";
    $("#stream-rows").replaceChildren(...data.streams.map(stream => {
      const row = element("tr");
      const view = element("button", "link-button", "Ver entradas");
      view.type = "button";
      view.disabled = !stream.total;
      view.addEventListener("click", () => { $("#record-stream").value = stream.name; loaded.delete("records"); openTab("records"); });
      const action = element("td");
      action.append(view);
      row.append(
        element("td", "", stream.title),
        element("td", "num", stream.total.toLocaleString("es")),
        element("td", "num", stream.last_24h.toLocaleString("es")),
        element("td", "num", stream.last_7d.toLocaleString("es")),
        element("td", "", stream.last_at ? `${dateTime(stream.last_at)} · ${ago(stream.last_at)}` : "—"),
        action,
      );
      return row;
    }));
    if (!$("#record-stream").options.length) {
      for (const stream of data.streams) {
        const option = element("option", "", `${stream.title} (${stream.total.toLocaleString("es")})`);
        option.value = stream.name;
        $("#record-stream").append(option);
      }
    }
    $("#overview-status").textContent = "";
    return true;
  } catch (error) {
    if (accessError(error)) return false;
    $("#overview-status").textContent = `No se pudo cargar el resumen: ${error.message}`;
    return false;
  }
}

function summarize(data) {
  const parts = [data.type, data.event_type, data.preferred_report?.place || data.place, data.status, data.action, data.email, data.report_id || data.event_id];
  return parts.filter(value => typeof value === "string" && value).slice(0, 3).join(" · ") || "Entrada";
}
function renderRecords() {
  const query = $("#record-q").value.trim().toLocaleLowerCase("es");
  const visible = records.filter(record => !query || JSON.stringify(record.data).toLocaleLowerCase("es").includes(query));
  $("#record-list").replaceChildren(...visible.map(record => {
    const item = element("li");
    const details = element("details");
    const summary = element("summary");
    summary.append(element("time", "", dateTime(record.at)), element("span", "", summarize(record.data)));
    details.append(summary, element("pre", "", JSON.stringify(record.data, null, 2)));
    item.append(details);
    return item;
  }));
  $("#record-count").textContent = `${visible.length} de ${records.length} entradas mostradas`;
}
async function loadRecords() {
  if (!$("#record-stream").value && !await loadOverview()) return false;
  const name = $("#record-stream").value;
  const request = ++recordRequest;
  records = [];
  $("#record-list").replaceChildren();
  $("#record-count").textContent = "Cargando…";
  try {
    const data = await api(`/v1/admin/records/${encodeURIComponent(name)}?limit=${$("#record-limit").value}`);
    if (request !== recordRequest) return false;
    records = data.records;
    renderRecords();
    $("#record-count").textContent = `${records.length} de ${data.total.toLocaleString("es")} entradas · ${data.title}`;
    return true;
  } catch (error) {
    if (request !== recordRequest || accessError(error)) return false;
    $("#record-count").textContent = `No se pudo cargar el registro: ${error.message}`;
    loaded.delete("records");
    return false;
  }
}

function renderControls(controls) {
  $("#controls-list").replaceChildren(...controls.map(control => {
    const card = element("li", "control-card");
    const info = element("div");
    info.append(element("h2", "", control.label), element("p", "", control.paused ? "Pausado" : control.enabled ? "Activo" : control.worker_available ? "Sin configurar para envíos" : "Servicio sin conexión reciente"));
    const button = element("button", "button secondary compact keep", control.paused ? "Reanudar" : "Pausar");
    button.type = "button";
    button.disabled = controlsBusy || (control.paused && !control.configured);
    button.addEventListener("click", () => changeControl(control));
    card.append(info, button);
    return card;
  }));
}
async function loadControls() {
  const epoch = adminEpoch;
  if (controlsBusy) return false;
  $("#controls-status").textContent = "Consultando servicios…";
  try {
    const data = await api("/v1/admin/controls");
    if (epoch !== adminEpoch) return false;
    renderControls(data.controls);
    $("#controls-status").textContent = "";
    return true;
  } catch (error) {
    if (!accessError(error)) $("#controls-status").textContent = `No se pudo cargar el estado: ${error.message}`;
    return false;
  }
}
async function changeControl(control) {
  const verb = control.paused ? "reanudar" : "pausar";
  const approval = await approveAction(`control:${control.id}:${control.paused}`, `${verb} ${control.label.toLocaleLowerCase("es")}`);
  if (!approval) return;
  controlsBusy = true;
  for (const button of $("#controls-list").querySelectorAll("button")) button.disabled = true;
  $("#controls-status").textContent = "Guardando cambio…";
  try {
    const data = await api(`/v1/admin/controls/${encodeURIComponent(control.id)}`, {method:"PUT", approval, body:JSON.stringify({enabled:control.paused})});
    controlsBusy = false;
    renderControls(data.controls);
    $("#controls-status").textContent = `Cambio confirmado: ${control.label} ${control.paused ? "reanuda su funcionamiento" : "queda pausado"}.`;
  } catch (error) {
    controlsBusy = false;
    if (accessError(error)) return;
    await loadControls();
    $("#controls-status").textContent = `No se pudo confirmar el cambio: ${error.message}. Revisa el estado antes de reintentar.`;
  }
}

// El MFA aprueba una acción concreta: el servidor calcula esta misma huella con SHA-256.
async function sha16(text) {
  const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(bytes)].map(byte => byte.toString(16).padStart(2, "0")).join("").slice(0, 16);
}
function phoneDetails(phone) {
  const wrap = element("p");
  const chip = (text, tone) => wrap.append(element("span", `chip${tone ? ` ${tone}` : ""}`, text));
  chip(PLATFORMS[phone.platform] || "Sin registrar");
  chip(phone.push_ready ? "Listo para notificaciones" : phone.registered ? "Sin token de notificaciones" : "No registrado", phone.push_ready ? "ok" : "warn");
  if (phone.push_ready) chip(phone.critical_alerts ? "Alertas críticas permitidas" : "Sin alertas críticas");
  wrap.append(`…${phone.suffix}`);
  return wrap;
}
function updateDrillButton() {
  const count = [...picked].filter(ref => betaPhones.some(phone => phone.ref === ref && phone.push_ready)).length;
  $("#drill-send").disabled = betaBusy || !count;
  $("#drill-send").textContent = count ? `Enviar simulacro a ${count} teléfono${count === 1 ? "" : "s"}` : "Enviar simulacro";
}
function renderPhones() {
  for (const ref of [...picked]) if (!betaPhones.some(phone => phone.ref === ref)) picked.delete(ref);
  $("#beta-phones").replaceChildren(...(betaPhones.length ? betaPhones.map(phone => {
    const card = element("li", "control-card beta-phone");
    const info = element("div");
    info.append(element("h2", "", phone.label || "Sin nombre"), phoneDetails(phone));
    const pick = element("label", "pick");
    const box = element("input");
    box.type = "checkbox";
    box.checked = picked.has(phone.ref);
    box.disabled = !phone.push_ready;
    box.addEventListener("change", () => { box.checked ? picked.add(phone.ref) : picked.delete(phone.ref); updateDrillButton(); });
    pick.append(box, "Incluir en el simulacro");
    const remove = element("button", "button secondary compact keep", "Quitar");
    remove.type = "button";
    remove.disabled = betaBusy;
    remove.addEventListener("click", () => removePhone(phone));
    const actions = element("div", "pick");
    actions.append(pick, remove);
    card.append(info, actions);
    return card;
  }) : [Object.assign(element("li", "control-card"), {textContent: "Todavía no hay teléfonos inscritos."})]));
  updateDrillButton();
}
function renderDrills(drills) {
  $("#drill-list").replaceChildren(...(drills.length ? drills.map(drill => {
    const card = element("li", "control-card");
    const info = element("div");
    const result = drill.status === "sent" ? `Enviado a ${drill.succeeded || 0} de ${drill.attempted || drill.targets}` : DRILL_STATUS[drill.status] || drill.status;
    info.append(
      element("h2", "", `${drill.place || "Simulacro"} · M ${drill.magnitude || "?"} · ${drill.critical === "true" ? "alarma crítica" : "aviso normal"}`),
      element("p", "", `${dateTime(drill.at)} · ${ago(drill.at)} · ${drill.targets} teléfono${drill.targets === "1" ? "" : "s"}${drill.latitude ? ` · ${drill.latitude}, ${drill.longitude} · ${drill.depth_km} km` : ""}`),
    );
    card.append(info, element("span", "chip", result));
    return card;
  }) : [Object.assign(element("li", "control-card"), {textContent: "Aún no has enviado simulacros."})]));
  clearTimeout(drillPoll);
  // Un simulacro en cola se resuelve en segundos: se vuelve a consultar sin que lo pidas.
  if (drills.some(drill => drill.status === "queued" && Date.now() - new Date(drill.at) < 120_000)) {
    const epoch = adminEpoch;
    drillPoll = setTimeout(() => { if (epoch === adminEpoch) refreshDrills(); }, 3000);
  }
}
async function refreshDrills() {
  try { renderDrills((await api("/v1/admin/drills")).drills); }
  catch (error) { accessError(error); }
}
async function loadBeta() {
  const epoch = adminEpoch;
  $("#beta-status").textContent = "Cargando…";
  try {
    const [phones, drills] = await Promise.all([api("/v1/admin/beta-phones"), api("/v1/admin/drills")]);
    if (epoch !== adminEpoch) return false;
    betaPhones = phones.phones;
    if (!$("#drill-scenario").options.length) {
      betaScenarios = phones.scenarios;
      for (const scenario of phones.scenarios) {
        const option = element("option", "", `${scenario.place.replace("Simulacro — ", "")} · M ${scenario.magnitude.toFixed(1)}`);
        option.value = scenario.id;
        $("#drill-scenario").append(option);
      }
      applyTemplate();
    }
    renderPhones();
    renderDrills(drills.drills);
    $("#beta-status").textContent = "";
    return true;
  } catch (error) {
    if (!accessError(error)) $("#beta-status").textContent = `No se pudieron cargar los teléfonos: ${error.message}`;
    return false;
  }
}
async function betaChange(action, label, request, done) {
  const approval = await approveAction(action, label);
  if (!approval) return;
  betaBusy = true;
  renderPhones();
  $("#beta-status").textContent = "Guardando…";
  try {
    const data = await api(...request(approval));
    betaBusy = false;
    done(data);
  } catch (error) {
    betaBusy = false;
    renderPhones();
    if (!accessError(error)) $("#beta-status").textContent = `No se pudo completar: ${error.message}`;
  }
}
async function enrollPhone(event) {
  event.preventDefault();
  const deviceId = $("#beta-device").value.trim();
  const label = $("#beta-label").value.trim();
  if (!deviceId || !label) return;
  const ref = await sha16(deviceId);
  await betaChange(`beta:add:${ref}`, `inscribir «${label}» en la beta`,
    approval => ["/v1/admin/beta-phones", {method:"POST", approval, body:JSON.stringify({device_id:deviceId, label})}],
    data => {
      betaPhones = data.phones;
      $("#beta-device").value = "";
      $("#beta-label").value = "";
      renderPhones();
      $("#beta-status").textContent = `«${label}» quedó inscrito.`;
    });
}
async function removePhone(phone) {
  await betaChange(`beta:remove:${phone.ref}`, `quitar «${phone.label}» de la beta`,
    approval => [`/v1/admin/beta-phones/${phone.ref}`, {method:"DELETE", approval}],
    data => {
      betaPhones = data.phones;
      renderPhones();
      $("#beta-status").textContent = `«${phone.label}» ya no está en la beta.`;
    });
}
// Los mismos datos, con los mismos formatos, que firma el servidor (`drill_action` en admin_beta.py).
function readDrill(refs) {
  const form = $("#drill-form");
  if (!form.reportValidity()) return null;
  let place = $("#drill-place").value.trim().replace(/\s+/g, " ");
  if (!/^simulacro/i.test(place)) place = `Simulacro — ${place}`;
  return {
    critical: $("#drill-critical").checked,
    latitude: $("#drill-lat").valueAsNumber, longitude: $("#drill-lon").valueAsNumber,
    magnitude: $("#drill-mag").valueAsNumber, depth_km: $("#drill-depth").valueAsNumber,
    place, origin_minutes_ago: $("#drill-ago").valueAsNumber, country_code: $("#drill-country").value.trim().toUpperCase(), refs,
  };
}
async function drillAction(drill) {
  const parts = [
    drill.critical ? "critical" : "notice", drill.latitude.toFixed(4), drill.longitude.toFixed(4),
    drill.magnitude.toFixed(1), drill.depth_km.toFixed(1), String(drill.origin_minutes_ago), drill.country_code, drill.place,
    [...new Set(drill.refs)].sort().join(","),
  ];
  return `drill:${await sha16(parts.join("|"))}`;
}
function applyTemplate() {
  const template = betaScenarios.find(item => item.id === $("#drill-scenario").value);
  if (!template) return;
  $("#drill-place").value = template.place.replace("Simulacro — ", "");
  $("#drill-lat").value = template.latitude;
  $("#drill-lon").value = template.longitude;
  $("#drill-mag").value = template.magnitude.toFixed(1);
  $("#drill-depth").value = template.depth_km.toFixed(1);
  $("#drill-country").value = template.country_code;
}
async function sendDrill(event) {
  event.preventDefault();
  const refs = [...picked].filter(ref => betaPhones.some(phone => phone.ref === ref && phone.push_ready)).sort();
  if (!refs.length) return;
  const drill = readDrill(refs);
  if (!drill) return;
  const names = betaPhones.filter(phone => refs.includes(phone.ref)).map(phone => phone.label).join(", ");
  const label = `enviar «${drill.place}» (M ${drill.magnitude.toFixed(1)}, ${drill.depth_km.toFixed(1)} km, ${drill.latitude.toFixed(4)}, ${drill.longitude.toFixed(4)}) ${drill.critical ? "con alarma crítica" : "con aviso normal"} a: ${names}`;
  await betaChange(await drillAction(drill), label,
    approval => ["/v1/admin/drills", {method:"POST", approval, body:JSON.stringify(drill)}],
    data => {
      renderPhones();
      renderDrills(data.drills);
      $("#beta-status").textContent = "Simulacro enviado a la cola. Debería llegar en unos segundos.";
    });
}

async function start() {
  $("#status").textContent = "Comprobando acceso…";
  try {
    if (!await adminAuthenticate()) { $("#status").textContent = ""; return; }
    const me = await api("/v1/admin/me");
    showUser(me.email);
    $("#gate").hidden = true;
    $("#app").hidden = false;
    $("#status").textContent = "";
    openTab("overview");
  } catch (error) {
    $("#status").textContent = "";
    if (error.status === 401) {
      showUser("");
      showGate("Administración de Seismik", "Inicia sesión en auth.seismik.org con la cuenta autorizada. Volverás aquí al terminar.");
    } else if (error.status === 403) {
      const session = {};
      showUser(session.email || "");
      showGate("Sin acceso", `${session.email || "Esta cuenta"} no tiene acceso a la administración. Sal e inicia sesión con la cuenta autorizada.`, {login:false, switchAccount:true});
    } else {
      showGate("No disponible", `No se pudo comprobar el acceso: ${error.message}`);
    }
  }
}

$("#gate-login").addEventListener("click", login);
$("#gate-switch").addEventListener("click", async () => { await logout(); login(); });
$("#logout-button").addEventListener("click", logout);
for (const tab of document.querySelectorAll("[data-tab]")) tab.addEventListener("click", () => openTab(tab.dataset.tab));
$("#overview-reload").addEventListener("click", loadOverview);
$("#record-stream").addEventListener("change", loadRecords);
$("#record-limit").addEventListener("change", loadRecords);
$("#record-reload").addEventListener("click", loadRecords);
$("#controls-reload").addEventListener("click", loadControls);
$("#beta-reload").addEventListener("click", loadBeta);
$("#beta-form").addEventListener("submit", enrollPhone);
$("#drill-form").addEventListener("submit", sendDrill);
$("#drill-scenario").addEventListener("change", applyTemplate);
$("#record-q").addEventListener("input", renderRecords);
$("#record-form").addEventListener("submit", event => event.preventDefault());
start();
window.addEventListener("pageshow", event => { if (event.persisted) { clearData(); start(); } });
