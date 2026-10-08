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
  web_sessions:"Sesiones web abiertas",
  app_sessions:"Sesiones de la app",
};
const loaded = new Set();
let records = [];

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

// auth.seismik.org vuelve aquí si encuentra esta marca de 10 minutos. SameSite=None
// porque Apple devuelve el inicio de sesión con un POST desde su dominio.
function login() {
  document.cookie = "seismik_after_login=admin; Domain=.seismik.org; Path=/; Max-Age=600; Secure; SameSite=None";
  window.location.assign(AUTH_URL);
}
async function logout() {
  await api("/v1/oauth/logout", {method:"POST"}).catch(() => {});
  loaded.clear();
  reports = [];
  records = [];
  for (const selector of ["#rows", "#record-list", "#key-stats", "#stream-rows", "#stats"]) $(selector).replaceChildren();
  $("#export").disabled = true;
  start();
}

function openTab(name) {
  for (const tab of document.querySelectorAll("[data-tab]")) tab.setAttribute("aria-selected", String(tab.dataset.tab === name));
  for (const panel of document.querySelectorAll("[role=tabpanel]")) panel.hidden = panel.id !== `tab-${name}`;
  if (loaded.has(name)) return;
  loaded.add(name);
  if (name === "overview") loadOverview();
  if (name === "reports") loadReports();
  if (name === "records") loadRecords();
}

async function loadOverview() {
  $("#overview-status").textContent = "Cargando…";
  try {
    const data = await api("/v1/admin/overview");
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
      view.addEventListener("click", () => { $("#record-stream").value = stream.name; loaded.add("records"); openTab("records"); loadRecords(); });
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
  } catch (error) {
    $("#overview-status").textContent = `No se pudo cargar el resumen: ${error.message}`;
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
  const name = $("#record-stream").value;
  if (!name) { await loadOverview(); if (!$("#record-stream").value) return; }
  $("#record-count").textContent = "Cargando…";
  try {
    const data = await api(`/v1/admin/records/${encodeURIComponent($("#record-stream").value)}?limit=${$("#record-limit").value}`);
    records = data.records;
    renderRecords();
    $("#record-count").textContent = `${records.length} de ${data.total.toLocaleString("es")} entradas · ${data.title}`;
  } catch (error) {
    $("#record-count").textContent = `No se pudo cargar el registro: ${error.message}`;
  }
}

async function start() {
  $("#status").textContent = "Comprobando acceso…";
  try {
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
      const session = await api("/v1/oauth/session").catch(() => ({}));
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
$("#record-q").addEventListener("input", renderRecords);
$("#record-form").addEventListener("submit", event => event.preventDefault());
start();
window.addEventListener("pageshow", event => { if (event.persisted) { loaded.clear(); start(); } });
