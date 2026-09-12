// Same-origin proxy keeps the Seismik session cookie available to the portal.
const API = window.location.origin;
const AUTH = "https://auth.seismik.org";
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

function login() {
  window.location.assign(`${AUTH}/v1/oauth/authorize?origin=devs&provider=google`);
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
  return `<article class="key-row" data-key-id="${escapeHtml(key.key_id)}">
    <div class="key-name"><strong>${escapeHtml(key.name)}</strong><small>${escapeHtml(key.prefix)}</small></div>
    <div class="key-meta"><code>${escapeHtml(scopes)}</code><br><small>${key.requests_today.toLocaleString("es-CO")} hoy · último uso: ${formatDate(key.last_used_at)}</small></div>
    <span class="key-status ${key.status === "active" ? "active" : "revoked"}">${key.status === "active" ? "Activa" : "Revocada"}</span>
    <div class="key-actions">${key.status === "active" ? `<button class="text-button rotate-key" type="button">Rotar</button><button class="text-button danger-button revoke-key" type="button">Revocar</button>` : ""}</div>
  </article>`;
}

function escapeHtml(value) {
  // `textContent` no escapa comillas, y estos valores también se interpolan
  // dentro de atributos: sin ellas un valor con `"` se sale del atributo.
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

async function loadKeys() {
  try {
    const result = await api("/v1/developer/keys");
    elements["key-counter"].textContent = `${result.active_count} / ${result.active_limit}`;
    elements["keys-empty"].hidden = result.keys.length > 0;
    elements["keys-list"].innerHTML = result.keys.map(keyMarkup).join("");
  } catch (error) { toast(error.message, true); }
}

function webhookMarkup(webhook) {
  const types = webhook.event_types.map((item) => item === "earthquake_candidate" ? "candidato" : "oficial").join(" · ");
  return `<article class="key-row" data-webhook-id="${escapeHtml(webhook.webhook_id)}">
    <div class="key-name"><strong>${escapeHtml(webhook.name)}</strong><small>${escapeHtml(webhook.endpoint)}</small></div>
    <div class="key-meta"><code>${escapeHtml(types)}</code><br><small>Última entrega: ${formatDate(webhook.last_delivered_at)}${webhook.last_error ? ` · ${escapeHtml(webhook.last_error)}` : ""}</small></div>
    <span class="key-status ${webhook.status === "active" ? "active" : "revoked"}">${webhook.status === "active" ? "Activa" : "Desactivada"}</span>
    <div class="key-actions">${webhook.status === "active" ? '<button class="text-button danger-button disable-webhook" type="button">Desactivar</button>' : ""}</div>
  </article>`;
}

async function loadWebhooks() {
  try {
    const result = await api("/v1/developer/webhooks");
    elements["webhooks-empty"].hidden = result.webhooks.length > 0;
    elements["webhooks-list"].innerHTML = result.webhooks.map(webhookMarkup).join("");
  } catch (error) { toast(error.message, true); }
}

function webhookEventTypes() {
  return [...document.querySelectorAll('input[name="webhook-event"]:checked')].map((input) => input.value);
}

async function createWebhook(event) {
  event.preventDefault();
  try {
    const result = await api("/v1/developer/webhooks", {
      method: "POST",
      body: JSON.stringify({
        name: elements["webhook-name"].value.trim(),
        endpoint: elements["webhook-endpoint"].value.trim(),
        event_types: webhookEventTypes(),
        mode: "simulation_only",
      }),
    });
    elements["webhook-secret-value"].textContent = result.signing_secret;
    elements["webhook-secret-dialog"].showModal();
    event.target.reset();
    document.querySelector('input[name="webhook-event"][value="official_report_update"]').checked = true;
    await loadWebhooks();
  } catch (error) { toast(error.message, true); }
}

async function webhookAction(event) {
  const row = event.target.closest("[data-webhook-id]");
  if (!row || !event.target.classList.contains("disable-webhook")) return;
  if (!window.confirm("¿Desactivar este webhook? Dejará de recibir entregas.")) return;
  try {
    await api(`/v1/developer/webhooks/${row.dataset.webhookId}`, { method: "DELETE" });
    toast("Webhook desactivado.");
    await loadWebhooks();
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
  if (signedIn) {
    loadKeys();
    loadWebhooks();
  }
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
elements["webhook-form"].addEventListener("submit", createWebhook);
elements["webhooks-list"].addEventListener("click", webhookAction);
elements["refresh-webhooks-button"].addEventListener("click", loadWebhooks);
elements["copy-secret"].addEventListener("click", () => copyText(elements["secret-value"].textContent));
elements["copy-webhook-secret"].addEventListener("click", () => copyText(elements["webhook-secret-value"].textContent));
elements["copy-example"].addEventListener("click", () => copyText(elements["curl-example"].textContent));
boot();
