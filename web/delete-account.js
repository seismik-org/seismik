// El worker de Cloudflare enruta /v1/* de seismik.org hacia la API, igual que
// ya hace en devs.seismik.org: por eso una ruta relativa basta, sin CORS.
(() => {
  const form = document.querySelector("#delete-form");
  if (!form) return;

  const status = document.querySelector("#delete-form-status");
  const submitButton = form.querySelector("button[type=submit]");
  const turnstileContainer = document.querySelector("#turnstile-container");
  let turnstileWidgetId = null;
  let turnstileApiPromise = null;
  let formConfig = { enabled: false, site_key: null, action: null };

  function setStatus(message, state) {
    status.textContent = message;
    if (state) status.dataset.state = state;
    else delete status.dataset.state;
  }

  function setBusy(busy) {
    submitButton.disabled = busy;
    submitButton.setAttribute("aria-busy", busy ? "true" : "false");
  }

  function loadTurnstile() {
    if (window.turnstile) return Promise.resolve(window.turnstile);
    if (turnstileApiPromise) return turnstileApiPromise;
    turnstileApiPromise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
      script.async = true;
      script.onload = () => (window.turnstile ? resolve(window.turnstile) : reject(new Error("No se pudo cargar la verificación de seguridad.")));
      script.onerror = () => reject(new Error("No se pudo cargar la verificación de seguridad."));
      document.head.append(script);
    });
    return turnstileApiPromise;
  }

  async function renderTurnstile() {
    turnstileContainer.hidden = !formConfig.enabled;
    if (!formConfig.enabled || turnstileWidgetId !== null) return;
    try {
      const turnstile = await loadTurnstile();
      turnstileWidgetId = turnstile.render(turnstileContainer, {
        sitekey: formConfig.site_key,
        action: formConfig.action,
        language: "es",
      });
    } catch (error) {
      setStatus(error.message, "error");
    }
  }

  function turnstileToken() {
    if (!formConfig.enabled) return null;
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

  async function loadConfig() {
    try {
      const response = await fetch("/v1/account/deletion-config");
      if (response.ok) formConfig = await response.json();
    } catch (_error) {
      // Sin config disponible el formulario sigue funcionando: el servidor
      // decide si exige el token al recibir el envío.
    }
    await renderTurnstile();
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    setStatus("", null);

    let token;
    try {
      token = turnstileToken();
    } catch (error) {
      setStatus(error.message, "error");
      return;
    }

    const data = new FormData(form);
    const payload = {
      email: String(data.get("email") || "").trim(),
      scope: String(data.get("scope") || "full"),
      details: String(data.get("details") || "").trim() || null,
      turnstile_token: token,
    };

    setBusy(true);
    try {
      const response = await fetch("/v1/account/deletion-requests", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.detail || `Error ${response.status}`);
      setStatus(body.message || "Recibimos tu solicitud.", "ok");
      form.reset();
    } catch (error) {
      setStatus(error.message, "error");
    } finally {
      setBusy(false);
      resetTurnstile();
    }
  });

  loadConfig();
})();
