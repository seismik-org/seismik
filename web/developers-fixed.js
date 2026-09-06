// Same-origin proxy keeps the Seismik session cookie available to the portal.
const API = window.location.origin;
const elements = Object.fromEntries([...document.querySelectorAll("[id]")].map((item) => [item.id, item]));
let currentUser = null;
let portalConfig = null;

function toast(message, error = false) {
  elements.toast.textContent = message;
  elements.toast.classList.toggle("error", error);
  elements.toast.classList.add("visible");
  window.setTimeout(() => elements.toast.classList.remove("visible"), 3500);
}

async function api(path, options = {}, authenticated = true) {
  const headers = new Headers(options.headers || {});
  if (options.body) headers.set("Content-Type", "application/json");
  if (authenticated && !currentUser) throw new Error("Inicia sesión para continuar.");
  const response = await fetch(`${API}${path}`, { ...options, headers, credentials: "include" });
  if (!response.ok) {
    let detail = `Error ${response.status}`;
    try { detail = (await response.json()).detail || detail; } catch (_) { /* no JSON */ }
    throw new Error(detail);
  }
  if (response.status === 204) return null;
  return response.json();
}

async function login() {
  window.location.assign(`${API}/v1/oauth/google/start`);
}

async function copyText(value) {
  await navigator.clipboard.writeText(value);
  toast("Copiado al portapapeles.");
}

function formatDate(value) {
  if (!value) return "Sin uso";
  return new Intl.DateTimeFormat("es-CO", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function keyMarkup(key) {
  const scopes = key.scopes.map((scope) => scope.replace(":read", "")).join(" · ");
  return `<article class="key-row" data-key-id="${key.key_id}">
    <div class="key-name"><strong>${escapeHtml(key.name)}</strong><small>${escapeHtml(key.prefix)}</small></div>
    <div class="key-meta"><code>${escapeHtml(scopes)}</code><br><small>${key.requests_today.toLocaleString("es-CO")} hoy · último uso: ${formatDate(key.last_used_at)}</small></div>
    <span class="key-status ${key.status}">${key.status === "active" ? "Activa" : "Revocada"}</span>
    <div class="key-actions">${key.status === "active" ? `<button class="text-button rotate-key" type="button">Rotar</button><button class="text-button danger-button revoke-key" type="button">Revocar</button>` : ""}</div>
  </article>`;
}

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value;
  return div.innerHTML;
}

async function loadKeys() {
  try {
    const result = await api("/v1/developer/keys");
    elements["key-counter"].textContent = `${result.active_count} / ${result.active_limit}`;
    elements["keys-empty"].hidden = result.keys.length > 0;
    elements["keys-list"].innerHTML = result.keys.map(keyMarkup).join("");
  } catch (error) { toast(error.message, true); }
}

function selectedScopes() {
  return [...document.querySelectorAll('input[name="scope"]:checked')].map((input) => input.value);
}

function keyPayload() {
  return {
    name: elements["key-name"].value.trim(),
    scopes: selectedScopes(),
    accepted_terms_version: portalConfig.terms_version,
  };
}

function showSecret(result) {
  elements["secret-value"].textContent = result.key;
  elements["secret-dialog"].showModal();
}

async function createKey(event) {
  event.preventDefault();
  if (!elements["terms-checkbox"].checked) return;
  try {
    const result = await api("/v1/developer/keys", { method: "POST", body: JSON.stringify(keyPayload()) });
    showSecret(result);
    event.target.reset();
    document.querySelectorAll('input[name="scope"]').forEach((input) => { input.checked = true; });
    await loadKeys();
  } catch (error) { toast(error.message, true); }
}

async function keyAction(event) {
  const row = event.target.closest(".key-row");
  if (!row) return;
  const keyId = row.dataset.keyId;
  try {
    if (event.target.classList.contains("revoke-key")) {
      if (!window.confirm("¿Revocar esta clave? Las integraciones que la usen dejarán de funcionar.")) return;
      await api(`/v1/developer/keys/${keyId}`, { method: "DELETE" });
      toast("Clave revocada.");
    } else if (event.target.classList.contains("rotate-key")) {
      if (!window.confirm("La clave actual será revocada inmediatamente. ¿Continuar?")) return;
      const name = row.querySelector(".key-name strong").textContent;
      const scopes = row.querySelector(".key-meta code").textContent.split(" · ").map((value) => `${value}:read`);
      const result = await api(`/v1/developer/keys/${keyId}/rotate`, {
        method: "POST",
        body: JSON.stringify({ name: `${name} rotada`, scopes, accepted_terms_version: portalConfig.terms_version }),
      });
      showSecret(result);
    } else return;
    await loadKeys();
  } catch (error) { toast(error.message, true); }
}

function updateSession(user) {
  currentUser = user;
  const signedIn = Boolean(user);
  elements["signed-out-panel"].hidden = signedIn;
  elements["signed-in-panel"].hidden = !signedIn;
  elements["login-button"].hidden = signedIn;
  elements["logout-button"].hidden = !signedIn;
  elements["user-label"].hidden = !signedIn;
  elements["user-label"].textContent = user?.email || "";
  if (signedIn) loadKeys();
}

async function boot() {
  try {
    portalConfig = await api("/v1/developer/config", {}, false);
    const plan = portalConfig.plans[0];
    elements["minute-quota"].textContent = plan.requests_per_minute.toLocaleString("es-CO");
    elements["daily-quota"].textContent = plan.requests_per_day.toLocaleString("es-CO");
    elements["active-key-limit"].textContent = plan.max_active_keys;
    try {
      const session = await api("/v1/oauth/session", {}, false);
      updateSession(session);
    } catch (_) {
      updateSession(null);
    }
  } catch (error) { toast(`No fue posible cargar la plataforma: ${error.message}`, true); }
}

elements["login-button"].addEventListener("click", login);
elements["panel-login-button"].addEventListener("click", login);
elements["logout-button"].addEventListener("click", async () => {
  await api("/v1/oauth/logout", { method: "POST" }, false);
  window.location.reload();
});
elements["key-form"].addEventListener("submit", createKey);
elements["refresh-button"].addEventListener("click", loadKeys);
elements["keys-list"].addEventListener("click", keyAction);
elements["copy-secret"].addEventListener("click", () => copyText(elements["secret-value"].textContent));
elements["copy-example"].addEventListener("click", () => copyText(elements["curl-example"].textContent));
boot();
