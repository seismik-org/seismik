// Same-origin proxy keeps the Seismik session cookie available to the portal.
const API = window.location.origin;
const AUTH = "https://auth.seismik.org";
const elements = Object.fromEntries([...document.querySelectorAll("[id]")].map((item) => [item.id, item]));
let currentUser = null;
let portalConfig = null;
let turnstileWidgetId = null;
let turnstileApiPromise = null;
let toastTimeout = null;

function toast(message, error = false) {
  window.clearTimeout(toastTimeout);
  elements.toast.textContent = message;
  elements.toast.setAttribute("role", error ? "alert" : "status");
  elements.toast.setAttribute("aria-live", error ? "assertive" : "polite");
  elements.toast.classList.toggle("error", error);
  elements.toast.classList.add("visible");
  toastTimeout = window.setTimeout(() => elements.toast.classList.remove("visible"), 3500);
}

function confirmAction({ eyebrow = "Acción sensible", title, message, confirmLabel, destructive = true }) {
  const dialog = elements["confirmation-dialog"];
  const accept = elements["confirmation-accept"];
  const cancel = elements["confirmation-cancel"];
  elements["confirmation-eyebrow"].textContent = eyebrow;
  elements["confirmation-title"].textContent = title;
  elements["confirmation-message"].textContent = message;
  accept.textContent = confirmLabel;
  accept.classList.toggle("button-danger", destructive);

  return new Promise((resolve) => {
    let settled = false;
    const cleanup = () => {
      accept.removeEventListener("click", approve);
      cancel.removeEventListener("click", dismiss);
      dialog.removeEventListener("cancel", dismiss);
      dialog.removeEventListener("close", onClose);
    };
    const finish = (confirmed) => {
      if (settled) return;
      settled = true;
      cleanup();
      if (dialog.open) dialog.close();
      resolve(confirmed);
    };
    const approve = () => finish(true);
    const dismiss = (event) => {
      event?.preventDefault();
      finish(false);
    };
    const onClose = () => finish(false);
    accept.addEventListener("click", approve);
    cancel.addEventListener("click", dismiss);
    dialog.addEventListener("cancel", dismiss);
    dialog.addEventListener("close", onClose);
    dialog.showModal();
    accept.focus();
  });
}

function setButtonBusy(button, busy, label) {
  if (!button) return;
  if (busy) {
    button.dataset.originalLabel = button.textContent;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    button.textContent = label;
    return;
  }
  button.disabled = false;
  button.removeAttribute("aria-busy");
  if (button.dataset.originalLabel) button.textContent = button.dataset.originalLabel;
  delete button.dataset.originalLabel;
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
  window.location.assign(`${AUTH}/id`);
}

function humanVerificationEnabled() {
  return Boolean(portalConfig?.human_verification?.enabled && portalConfig?.human_verification?.site_key);
}

function loadTurnstile() {
  if (window.turnstile) return Promise.resolve(window.turnstile);
  if (turnstileApiPromise) return turnstileApiPromise;
  turnstileApiPromise = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
    script.async = true;
    script.onload = () => window.turnstile ? resolve(window.turnstile) : reject(new Error("No se pudo cargar la verificación de seguridad."));
    script.onerror = () => reject(new Error("No se pudo cargar la verificación de seguridad."));
    document.head.append(script);
  });
  return turnstileApiPromise;
}

async function renderTurnstile() {
  const enabled = Boolean(currentUser) && humanVerificationEnabled();
  elements["turnstile-container"].hidden = !enabled;
  if (!enabled || turnstileWidgetId !== null) return;
  const turnstile = await loadTurnstile();
  turnstileWidgetId = turnstile.render(elements["turnstile-container"], {
    sitekey: portalConfig.human_verification.site_key,
    action: portalConfig.human_verification.action,
    language: "es",
    // Sin esto, un widget que se cae (pasa en producción, no sólo en teoría)
    // lanza una excepción sin capturar: el envío se pierde en silencio y
    // Cloudflare nunca ve la verificación del lado del servidor. Cloudflare
    // ya reintenta solo; aquí sólo se avisa y se deja continuar el reintento.
    "error-callback": () => {
      toast("La verificación de seguridad tuvo un problema; reintentando…", true);
      return false;
    },
    "expired-callback": () => toast("La verificación de seguridad expiró; vuelve a intentarlo.", true),
  });
}

function turnstileToken() {
  if (!humanVerificationEnabled()) return null;
  if (turnstileWidgetId === null || !window.turnstile) {
    throw new Error("Carga la verificación de seguridad antes de continuar.");
  }
  const token = window.turnstile.getResponse(turnstileWidgetId);
  if (!token) throw new Error("Completa la verificación de seguridad para continuar.");
  return token;
}

function resetTurnstile() {
  if (turnstileWidgetId !== null && window.turnstile) window.turnstile.reset(turnstileWidgetId);
}

async function copyText(value) {
  await navigator.clipboard.writeText(value);
  toast("Copiado al portapapeles.");
}

function formatDate(value) {
  if (!value) return "Sin uso";
  return new Intl.DateTimeFormat("es-CO", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function usdFromMicrounits(value, options = {}) {
  return new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD",
    minimumFractionDigits: options.minimumFractionDigits ?? 2,
    maximumFractionDigits: options.maximumFractionDigits ?? 2,
  }).format(Number(value) / portalConfig.billing.microunits_per_usd);
}

function creditPackMarkup(pack) {
  return `<article class="credit-pack"><p class="eyebrow">${escapeHtml(pack.name)}</p><h3>Créditos prepago</h3><strong>${usdFromMicrounits(pack.usd_microunits)}</strong><p>Saldo de uso en USD; no se renueva automáticamente.</p><small>Checkout próximamente</small></article>`;
}

function requestPriceMarkup(price) {
  return `<div class="request-price-row"><span>${escapeHtml(price.name)}<br><small>${escapeHtml(price.scope)}</small></span><strong>${usdFromMicrounits(price.usd_microunits_per_request, { minimumFractionDigits: 4, maximumFractionDigits: 4 })}</strong></div>`;
}

function renderBillingCatalog() {
  if (!portalConfig?.billing) return;
  elements["credit-packs"].innerHTML = portalConfig.billing.credit_packs.map(creditPackMarkup).join("");
  elements["request-prices"].innerHTML = portalConfig.billing.request_prices.map(requestPriceMarkup).join("");
}

function keyMarkup(key) {
  const scopes = key.scopes.map((scope) => scope.replace(":read", "")).join(" · ");
  return `<article class="key-row" data-key-id="${escapeHtml(key.key_id)}">
    <div class="key-name"><strong>${escapeHtml(key.name)}</strong><small>${escapeHtml(key.prefix)}</small></div>
    <div class="key-meta"><code>${escapeHtml(scopes)}</code><br><small>${key.requests_today.toLocaleString("es-CO")} hoy · último uso: ${formatDate(key.last_used_at)}</small></div>
    <span class="key-status ${key.status === "active" ? "active" : "revoked"}">${key.status === "active" ? "Activa" : "Revocada"}</span>
    <div class="key-actions">${key.status === "active" ? `<button class="text-button rotate-key" type="button" aria-label="Rotar ${escapeHtml(key.name)}">Rotar</button><button class="text-button danger-button revoke-key" type="button" aria-label="Revocar ${escapeHtml(key.name)}">Revocar</button>` : ""}</div>
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
    <div class="key-actions">${webhook.status === "active" ? `<button class="text-button danger-button disable-webhook" type="button" aria-label="Desactivar ${escapeHtml(webhook.name)}">Desactivar</button>` : ""}</div>
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
  const button = event.target.closest(".disable-webhook");
  if (!row || !button) return;
  const confirmed = await confirmAction({
    title: "¿Desactivar este webhook?",
    message: "Dejará de recibir entregas de Seismik. Podrás crear otro webhook si más adelante vuelves a necesitarlo.",
    confirmLabel: "Desactivar webhook",
  });
  if (!confirmed) return;
  setButtonBusy(button, true, "Desactivando…");
  try {
    await api(`/v1/developer/webhooks/${row.dataset.webhookId}`, { method: "DELETE" });
    toast("Webhook desactivado.");
    await loadWebhooks();
  } catch (error) { toast(error.message, true); } finally { setButtonBusy(button, false); }
}

function selectedScopes() {
  return [...document.querySelectorAll('input[name="scope"]:checked')].map((input) => input.value);
}

function keyPayload() {
  return {
    name: elements["key-name"].value.trim(),
    scopes: selectedScopes(),
    accepted_terms_version: portalConfig.terms_version,
    turnstile_token: turnstileToken(),
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
  } catch (error) { toast(error.message, true); } finally { resetTurnstile(); }
}

async function keyAction(event) {
  const row = event.target.closest(".key-row");
  if (!row) return;
  const keyId = row.dataset.keyId;
  const revokeButton = event.target.closest(".revoke-key");
  const rotateButton = event.target.closest(".rotate-key");
  try {
    if (revokeButton) {
      const confirmed = await confirmAction({
        title: "¿Revocar esta clave?",
        message: "Las integraciones que la usan dejarán de funcionar inmediatamente. Esta acción no se puede deshacer.",
        confirmLabel: "Revocar clave",
      });
      if (!confirmed) return;
      setButtonBusy(revokeButton, true, "Revocando…");
      await api(`/v1/developer/keys/${keyId}`, { method: "DELETE" });
      toast("Clave revocada.");
    } else if (rotateButton) {
      const confirmed = await confirmAction({
        eyebrow: "Renovar credencial",
        title: "¿Rotar esta clave?",
        message: "La clave actual se revocará de inmediato. Guarda y actualiza la nueva clave en tus integraciones antes de continuar.",
        confirmLabel: "Rotar clave",
      });
      if (!confirmed) return;
      setButtonBusy(rotateButton, true, "Rotando…");
      const name = row.querySelector(".key-name strong").textContent;
      const scopes = row.querySelector(".key-meta code").textContent.split(" · ").map((value) => `${value}:read`);
      const result = await api(`/v1/developer/keys/${keyId}/rotate`, {
        method: "POST",
        body: JSON.stringify({ name: `${name} rotada`, scopes, accepted_terms_version: portalConfig.terms_version, turnstile_token: turnstileToken() }),
      });
      showSecret(result);
    } else return;
    await loadKeys();
  } catch (error) { toast(error.message, true); } finally {
    setButtonBusy(revokeButton, false);
    setButtonBusy(rotateButton, false);
    resetTurnstile();
  }
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
    renderTurnstile().catch((error) => toast(error.message, true));
    loadKeys();
    loadWebhooks();
  }
}

async function boot() {
  try {
    const [configResult, sessionResult] = await Promise.allSettled([
      api("/v1/developer/config", {}, false),
      api("/v1/oauth/session", {}, false),
    ]);
    if (configResult.status === "rejected") throw configResult.reason;
    portalConfig = configResult.value;
    renderBillingCatalog();
    const plan = portalConfig.plans[0];
    elements["minute-quota"].textContent = plan.requests_per_minute.toLocaleString("es-CO");
    elements["daily-quota"].textContent = plan.requests_per_day.toLocaleString("es-CO");
    elements["active-key-limit"].textContent = plan.max_active_keys;
    updateSession(sessionResult.status === "fulfilled" ? sessionResult.value : null);
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
// Una restauración desde la caché de navegación puede conservar una sesión
// anterior. Revalidarla evita mostrar un panel desactualizado sin bloquear la
// restauración instantánea de la página.
window.addEventListener("pageshow", (event) => {
  if (event.persisted) boot();
});
