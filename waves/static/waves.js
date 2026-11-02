import {downloadRecord} from "/assets/download.js";
const $ = id => document.getElementById(id);
const PAGE = 25;
const GROUP_LABELS = {audit: "Auditoría de candidatos", evaluation: "Evaluación de magnitud", historical: "Históricos de referencia", cases: "Casos de estudio", fixtures: "Pruebas de reproducción"};
let offset = 0, total = 0, sessionVersion = 0, canDownload = false;
const resourcesHeading = document.createElement("h3"); resourcesHeading.textContent = "Metadatos y estudios de estaciones";
const resourcesStatus = document.createElement("p"); resourcesStatus.id = "resources-status"; resourcesStatus.setAttribute("role", "status");
const resourcesArea = document.createElement("div"); resourcesArea.id = "resources"; resourcesArea.className = "groups";
$("catalog-panel").append(resourcesHeading, resourcesStatus, resourcesArea);
const MB = value => value < 1e6
  ? `${(value / 1e3).toLocaleString("es-CO", {maximumFractionDigits: 1})} kB`
  : `${(value / 1e6).toLocaleString("es-CO", {maximumFractionDigits: value < 1e7 ? 1 : 0})} MB`;
const when = iso => iso ? iso.replace("T", " ").slice(0, 16) : "—";
const span = seconds => seconds >= 120 ? `${Math.round(seconds / 60)} min` : `${Math.round(seconds)} s`;
function status(text, error = false) { $("session-status").textContent = text; $("session-status").dataset.state = error ? "error" : "ok"; }
function clearCatalog() { $("catalog-panel").hidden = true; $("records").replaceChildren(); $("resources").replaceChildren(); offset = 0; }

async function loadResources(version) {
  try {
    const data = await api("/v1/waves/resources");
    if (version !== sessionVersion) return;
    $("resources").replaceChildren(...data.items.map(item => {
      const card = document.createElement("article"); card.className = "group";
      const title = document.createElement("h3"); title.textContent = item.title;
      const detail = document.createElement("p"); detail.textContent = item.description;
      const source = document.createElement("p"); source.textContent = `${item.provider} · ${item.format} · ${MB(item.bytes)}`;
      const hash = document.createElement("details"); const label = document.createElement("summary"); label.textContent = "Procedencia e integridad";
      const fingerprint = document.createElement("code"); fingerprint.textContent = `SHA-256: ${item.sha256}`; hash.append(label, fingerprint);
      if (item.source_url) { const link = document.createElement("a"); link.href = item.source_url; link.textContent = "Fuente ↗"; link.rel = "noopener noreferrer"; link.target = "_blank"; hash.append(link); }
      card.append(title, detail, source, hash);
      if (data.downloads_enabled) { const button = document.createElement("button"); button.type = "button"; button.className = "button compact secondary"; button.textContent = "Descargar recurso";
        button.onclick = () => downloadRecord(item.id, button, text => { $("resources-status").textContent = text; }, true); card.append(button); }
      return card;
    }));
    $("resources-status").textContent = `${data.items.length} recursos auxiliares. Investigación; cada fuente conserva sus condiciones de uso.`;
  } catch (error) { if (version === sessionVersion) $("resources-status").textContent = error.message; }
}

// La sesión es la cookie de Seismik (HttpOnly): esta página nunca la ve ni la guarda. Cada consulta la envía el
// navegador y el servidor decide, comprobándola con la API de Seismik, quién eres y si estás aprobado.
async function api(path, options = {}) {
  const response = await fetch(path, {cache: "no-store", credentials: "same-origin", ...options});
  const result = response.status === 204 ? {} : await response.json().catch(() => ({}));
  if (!response.ok) { const error = new Error(result.detail || "No se pudo consultar Waves."); error.status = response.status; throw error; }
  return result;
}

function renderGroups(summary) {
  const groups = $("groups");
  groups.replaceChildren();
  for (const item of summary.groups ?? []) {
    const card = document.createElement("article"); card.className = "group";
    const count = document.createElement("strong"); count.textContent = item.recordings.toLocaleString("es-CO");
    const unit = document.createElement("span"); unit.className = "group-unit"; unit.textContent = item.recordings === 1 ? "grabación" : "grabaciones";
    const title = document.createElement("h3"); title.textContent = item.label;
    const text = document.createElement("p"); text.textContent = item.description;
    const size = document.createElement("p"); size.className = "group-size"; size.textContent = `${MB(item.bytes)} · ${summary.formats?.join(", ") ?? "MiniSEED"}`;
    card.append(count, unit, title, text, size); groups.append(card);
  }
  const extra = summary.files - summary.waveforms;
  const note = $("groups-note");
  if (extra > 0) { note.textContent = `El archivo tiene ${summary.files.toLocaleString("es-CO")} archivos: ${summary.waveforms.toLocaleString("es-CO")} MiniSEED y ${extra.toLocaleString("es-CO")} de calibración y metadatos. ${summary.resource_files ?? 0} recursos auxiliares del suplemento se consultan por separado al iniciar sesión.`; note.hidden = false; }
}

function cell(text, className) { const td = document.createElement("td"); td.textContent = text; if (className) td.className = className; return td; }
function row(item) {
  const view = item.view ?? {};
  const tr = document.createElement("tr");
  const title = document.createElement("td"); title.className = "event-cell";
  const link = document.createElement("a"); link.href = `/explore?id=${encodeURIComponent(item.id)}`; link.textContent = view.title || item.name;
  const sub = document.createElement("small"); sub.textContent = view.reference ? `Referencia: ${view.reference}` : item.name.split("/").pop();
  title.append(link, document.createElement("br"), sub);
  const magnitude = typeof view.magnitude === "number" ? `${view.magnitude.toFixed(1)}${view.magnitude_type ? ` ${view.magnitude_type}` : ""}` : "—";
  const open = document.createElement("td"); const buttons = document.createElement("div"); buttons.className = "row-actions"; open.append(buttons);
  const go = document.createElement("a"); go.href = link.href; go.className = "button compact secondary"; go.textContent = "Ver ondas"; buttons.append(go);
  if (canDownload) {
    const save = document.createElement("button"); save.type = "button"; save.className = "button compact"; save.textContent = "Descargar";
    save.title = "Descargar el MiniSEED completo"; save.addEventListener("click", () => downloadRecord(item.id, save, (text, error) => status(text, error)));
    buttons.append(save);
  }
  tr.append(cell(when(view.origin_time || view.start), "nowrap"), title, cell(magnitude, "nowrap"), cell(view.stations ?? "—", "nowrap"), cell(view.duration_s ? span(view.duration_s) : "—", "nowrap"),
    cell(GROUP_LABELS[item.group] ?? item.category, "group-cell"), open);
  return tr;
}

async function catalog() {
  const version = sessionVersion;
  $("catalog-status").textContent = "Consultando grabaciones…";
  try {
    const params = new URLSearchParams({q: $("search").value, kind: $("kind").value, group: $("group").value,
      minimum_magnitude: $("minimum").value, sort: $("sort").value, offset, limit: PAGE});
    const result = await api(`/v1/waves/catalog?${params}`);
    if (version !== sessionVersion) return;
    total = result.total; $("records").replaceChildren(...result.items.map(row));
    $("catalog-status").textContent = total ? `${offset + 1}–${Math.min(offset + PAGE, total)} de ${total.toLocaleString("es-CO")} grabaciones. Archivo histórico, no eventos en vivo.` : "No hay grabaciones que coincidan con la búsqueda.";
    $("previous").disabled = offset === 0; $("next").disabled = offset + PAGE >= total;
  } catch (error) { if (version === sessionVersion) { clearCatalog(); status(error.message, true); } }
}

// El botón de arriba y el de la portada siguen el estado de la sesión: nunca piden acceder a quien ya entró.
function chrome(state, email = "") {
  const action = $("header-action"), hero = $("hero-action"), user = $("header-user");
  const approved = state === "approved", signedIn = state !== "anonymous";
  action.textContent = approved ? "Explorar archivo" : signedIn ? "Mi sesión" : "Acceder";
  action.href = approved ? "#catalog-panel" : "#acceso";
  hero.firstChild.textContent = approved ? "Explorar el archivo " : signedIn ? "Ver mi acceso " : "Acceder al piloto ";
  hero.href = action.href;
  user.hidden = !signedIn; user.textContent = email;
  $("header-logout").hidden = !signedIn;
  $("logout").hidden = !signedIn; $("login").hidden = signedIn;
}

async function checkSession() {
  const version = ++sessionVersion; clearCatalog();
  try {
    const session = await api("/v1/waves/session");
    if (version !== sessionVersion) return;
    if (!session.approved) { chrome("pending", session.email); status(`Sesión iniciada con ${session.email}. Tu cuenta aún no tiene acceso al piloto; solicítalo por correo.`); return; }
    canDownload = session.downloads_enabled === true;
    chrome("approved", session.email);
    status(`Acceso aprobado para ${session.email}.`); $("catalog-panel").hidden = false; await Promise.all([catalog(), loadResources(version)]);
  } catch (error) {
    if (version !== sessionVersion) return;
    chrome("anonymous");
    if (error.status === 401) status("Inicia sesión con tu cuenta Seismik para comprobar tu acceso. La inscripción al piloto requiere aprobación.");
    else status(error.message, true);
  }
}

async function logout(button) {
  button.disabled = true;
  try { await api("/v1/waves/logout", {method: "POST"}); }
  catch (error) { status(error.message, true); button.disabled = false; return; }
  button.disabled = false; await checkSession();
}

async function initialize() {
  try {
    const summary = await api("/v1/waves/summary");
    $("waveforms").textContent = summary.waveforms.toLocaleString("es-CO");
    $("volume").textContent = MB(summary.bytes);
    renderGroups(summary);
  } catch {
    $("waveforms").textContent = "No disponible"; $("volume").textContent = "No disponible";
    $("groups").textContent = "El resumen del archivo no está disponible en este momento.";
  }
  $("logout").addEventListener("click", () => logout($("logout")));
  $("header-logout").addEventListener("click", () => logout($("header-logout")));
  $("search-form").addEventListener("submit", event => { event.preventDefault(); offset = 0; catalog(); });
  for (const id of ["kind", "minimum", "sort"]) $(id).addEventListener("change", () => { offset = 0; catalog(); });
  $("group").addEventListener("change", () => {
    if ($("group").value === "audit") { $("kind").value = "caso"; $("minimum").value = "0"; }
    offset = 0; catalog();
  });
  $("previous").addEventListener("click", () => { offset = Math.max(0, offset - PAGE); catalog(); });
  $("next").addEventListener("click", () => { if (offset + PAGE < total) { offset += PAGE; catalog(); } });
  await checkSession();
}
initialize();
