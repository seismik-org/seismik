// Eliminación inmediata para quien ya inició sesión: la identidad queda probada por la sesión del portal,
// así que no hace falta que una persona verifique nada por correo. La ruta relativa llega a la API por el
// mismo enrutador de seismik.org que usa el formulario (sin CORS; la cookie de sesión viaja sola).
(() => {
  const panel = document.querySelector("#self-erase");
  if (!panel) return;

  const $ = (selector) => panel.querySelector(selector);
  const views = { loading: $("#self-loading"), out: $("#self-signed-out"), ready: $("#self-ready"), done: $("#self-done") };
  const status = $("#self-status");
  const word = $("#self-word");
  const confirmButton = $("#self-confirm");
  const reauth = $("#self-reauth");

  function show(name) {
    for (const [key, node] of Object.entries(views)) node.hidden = key !== name;
  }

  function setStatus(message, state) {
    status.textContent = message;
    if (state) status.dataset.state = state;
    else delete status.dataset.state;
  }

  function list(node, items) {
    node.replaceChildren(...items.map((text) => Object.assign(document.createElement("li"), { textContent: text })));
  }

  function counts(summary) {
    const parts = [];
    if (summary.devices) parts.push(`${summary.devices} dispositivo${summary.devices === 1 ? "" : "s"}`);
    if (summary.in_family_circle) parts.push("tu lugar en un círculo familiar");
    if (summary.api_keys) parts.push(`${summary.api_keys} clave${summary.api_keys === 1 ? "" : "s"} de API`);
    return parts.length ? `Ahora mismo tienes: ${parts.join(", ")}.` : "Ahora mismo no tienes dispositivos ni claves vinculados.";
  }

  async function load() {
    try {
      const response = await fetch("/v1/account/erasure", { headers: { Accept: "application/json" } });
      if (response.status === 401) return show("out");
      if (!response.ok) throw new Error(`Error ${response.status}`);
      const summary = await response.json();
      $("#self-who").textContent = `${summary.name ? summary.name + " · " : ""}${summary.email}`;
      $("#self-counts").textContent = counts(summary);
      list($("#self-erased"), summary.erased);
      list($("#self-retained"), summary.retained);
      reauth.hidden = summary.recent_login;
      word.disabled = !summary.recent_login;
      confirmButton.disabled = true;  // se habilita al escribir la palabra exacta
      show("ready");
      if (location.hash === "#confirmar") panel.scrollIntoView({ block: "start" });
    } catch {
      show("out");
    }
  }

  word.addEventListener("input", () => {
    confirmButton.disabled = word.disabled || word.value.trim() !== "ELIMINAR";
  });

  confirmButton.addEventListener("click", async () => {
    if (word.value.trim() !== "ELIMINAR") return;
    confirmButton.disabled = true;
    confirmButton.setAttribute("aria-busy", "true");
    setStatus("Eliminando…");
    try {
      const response = await fetch("/v1/account/erasure", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ confirm: "ELIMINAR" }),
      });
      const body = await response.json().catch(() => ({}));
      if (response.status === 401 && body.detail === "reauth_required") {
        reauth.hidden = false;
        word.disabled = true;
        throw new Error("Por seguridad, vuelve a iniciar sesión y confirma de nuevo.");
      }
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : `Error ${response.status}`);
      $("#self-pending").hidden = !(body.pending && body.pending.length);
      $("#self-retained-note").hidden = !body.billing_retained;
      show("done");
    } catch (error) {
      setStatus(error.message, "error");
      confirmButton.disabled = word.disabled || word.value.trim() !== "ELIMINAR";
    } finally {
      confirmButton.removeAttribute("aria-busy");
    }
  });

  load();
})();
