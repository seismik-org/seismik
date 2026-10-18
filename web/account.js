// Centro de la cuenta (auth.seismik.org/account). La API vive bajo /v1/oauth/ porque el Worker sólo enruta
// esa ruta del dominio de acceso hacia la API; la cookie de sesión viaja sola por ser del mismo origen.
(() => {
  const $ = (id) => document.getElementById(id);
  const API = "/v1/oauth/account";

  const NOTICES = {
    ok: ["Acceso vinculado. Desde ahora puedes entrar con él y llegarás a esta misma cuenta.", false],
    already: ["Ese acceso ya estaba vinculado a tu cuenta.", false],
    duplicate: ["Ya tienes un acceso de ese tipo vinculado. Quítalo primero si quieres usar otro.", true],
    conflict: ["No se pudo vincular: esa identidad ya tiene su propia cuenta en Seismik o está vinculada a otra persona. No fusionamos cuentas.", true],
    expired: ["El enlace caducó o se abrió en otro navegador. Vuelve a intentarlo desde aquí.", true],
    reauth: ["Por seguridad, vuelve a iniciar sesión y repite la vinculación.", true],
  };

  const DELETE_ITEMS = [
    { id: "devices", title: "Dispositivos", text: "Teléfonos registrados, sus tokens de notificaciones y su última ubicación." },
    { id: "family", title: "Círculo familiar", text: "Tu lugar en el círculo, tu alias, tus ubicaciones y estados compartidos." },
    { id: "developer", title: "Claves de API y webhooks", text: "Tus claves, tu perfil de desarrollador y tus webhooks." },
    { id: "reports", title: "Reportes enviados", text: "Los reportes de «sismo sentido» y de daños enviados desde tus dispositivos." },
  ];

  let center = null;

  function el(tag, props = {}, ...children) {
    const node = Object.assign(document.createElement(tag), props);
    for (const child of children.flat()) node.append(child);
    return node;
  }

  function show(name) {
    $("loading").hidden = name !== "loading";
    $("signed-out").hidden = name !== "out";
    $("signed-in").hidden = name !== "in";
  }

  function say(node, message, state) {
    node.textContent = message;
    if (state) node.dataset.state = state;
    else delete node.dataset.state;
  }

  function notice(message, error) {
    const node = $("notice");
    node.textContent = message;
    node.dataset.state = error ? "error" : "ok";
    node.hidden = false;
  }

  async function call(path, options = {}) {
    const response = await fetch(API + path, { headers: { Accept: "application/json" }, ...options });
    const body = await response.json().catch(() => ({}));
    if (response.status === 401 && body.detail === "reauth_required") {
      $("reauth").hidden = false;
      throw new Error("Por seguridad, vuelve a iniciar sesión (de los últimos 10 minutos) y repite la acción.");
    }
    if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : `Error ${response.status}`);
    return body;
  }

  // Un botón que pide una segunda pulsación antes de hacer algo que no se puede deshacer.
  function confirmButton(label, confirmLabel, run, className = "button secondary compact") {
    const button = el("button", { type: "button", className, textContent: label });
    let armed = false;
    let timer = 0;
    const reset = () => { armed = false; button.textContent = label; button.classList.remove("danger"); };
    button.addEventListener("click", async () => {
      if (!armed) {
        armed = true;
        button.textContent = confirmLabel;
        button.classList.add("danger");
        timer = window.setTimeout(reset, 6000);
        return;
      }
      window.clearTimeout(timer);
      button.disabled = true;
      try { await run(); } finally { button.disabled = false; reset(); }
    });
    return button;
  }

  function renderMethods() {
    const list = $("methods");
    list.replaceChildren(...center.methods.map((method) => {
      let chip;
      let action = null;
      if (method.primary) chip = el("span", { className: "chip chip-primary", textContent: "Principal" });
      else if (method.linked) {
        chip = el("span", { className: "chip chip-ok", textContent: "Vinculado" });
        if (method.removable) {
          action = confirmButton("Quitar", "¿Seguro? Pulsa de nuevo", async () => {
            try {
              const result = await call("/methods/unlink", {
                method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" },
                body: JSON.stringify({ method: method.id }),
              });
              center.methods = result.methods;
              renderMethods();
              notice(`Quitaste ${method.label}. Esa identidad ya no entra a esta cuenta.`, false);
            } catch (error) { notice(error.message, true); }
          });
        }
      } else {
        chip = el("span", { className: "chip", textContent: "Sin vincular" });
        action = method.linkable
          ? el("a", { className: "button secondary compact", href: `${API}/methods/link/${method.id}`, textContent: "Vincular" })
          : el("span", { className: "method-note", textContent: "Sólo como acceso principal" });
      }
      const hint = method.id === "email" && !method.linked
        ? "Se vincula entrando con tu correo en la página de acceso."
        : method.primary ? "Con este acceso se creó la cuenta." : "";
      return el("li", { className: "method" },
        el("div", { className: "method-info" }, el("strong", { textContent: method.label }), hint ? el("span", { textContent: hint }) : ""),
        el("div", { className: "method-actions" }, chip, action || ""));
    }));
  }

  function countText(data) {
    const parts = [];
    if (data.devices) parts.push(`${data.devices} dispositivo${data.devices === 1 ? "" : "s"}`);
    if (data.family_circle) parts.push("un círculo familiar");
    if (data.api_keys) parts.push(`${data.api_keys} clave${data.api_keys === 1 ? "" : "s"} de API`);
    if (data.webhooks) parts.push(`${data.webhooks} webhook${data.webhooks === 1 ? "" : "s"}`);
    if (data.reports) parts.push(`${data.reports} reporte${data.reports === 1 ? "" : "s"}`);
    if (data.billing) parts.push("registros de facturación");
    return parts.length ? `Seismik guarda: ${parts.join(", ")}.` : "Seismik no guarda dispositivos, círculos, claves ni reportes de esta cuenta.";
  }

  function renderDeleteList() {
    const counts = { devices: center.data.devices, family: center.data.family_circle ? 1 : 0, developer: center.data.api_keys + center.data.webhooks, reports: center.data.reports };
    $("delete-list").replaceChildren(...DELETE_ITEMS.map((item) => el("li", { className: "method" },
      el("div", { className: "method-info" }, el("strong", { textContent: item.title }), el("span", { textContent: item.text })),
      el("div", { className: "method-actions" },
        counts[item.id] === 0 ? el("span", { className: "method-note", textContent: "Nada que borrar" }) :
          confirmButton("Eliminar", "¿Seguro? Pulsa de nuevo", async () => {
            try {
              await call(`/data/${item.id}`, { method: "DELETE" });
              say($("delete-status"), `${item.title}: eliminado.`, "ok");
              await load(false);
            } catch (error) { say($("delete-status"), error.message, "error"); }
          })))));
    if (center.data.billing) $("delete-list").append(el("li", { className: "method-note-row", textContent: "Los registros contables de facturación se conservan por obligación legal." }));
  }

  function section(title, content) {
    return el("details", { className: "data-block", open: true }, el("summary", { textContent: title }), content);
  }

  function table(rows) {
    return el("dl", { className: "data-rows" }, rows.flatMap(([k, v]) => [el("dt", { textContent: k }), el("dd", { textContent: v === null || v === undefined || v === "" ? "—" : String(v) })]));
  }

  function renderDetail(data) {
    const blocks = [];
    blocks.push(section("Cuenta", table([["Nombre", data.cuenta.nombre], ["Correo", data.cuenta.correo], ["Identificador", data.cuenta.identificador],
      ["Accesos", data.cuenta.accesos.map((a) => a.metodo + (a.principal ? " (principal)" : "")).join(", ")]])));
    blocks.push(section(`Dispositivos (${data.dispositivos.length})`, data.dispositivos.length ? data.dispositivos.map((d) => table([
      ["Dispositivo", d.id], ["Plataforma", d.plataforma], ["Último registro", d.ultimo_registro],
      ["Ubicación guardada", d.ubicacion_guardada.latitud ? `${d.ubicacion_guardada.latitud}, ${d.ubicacion_guardada.longitud}` : null],
      ["Zona / país", [d.zona, d.pais].filter(Boolean).join(" / ")], ["Radio de alerta", d.alertas.radio_km ? `${d.alertas.radio_km} km` : null],
      ["Magnitud mínima", d.alertas.magnitud_minima], ["Alertas tempranas", d.alertas.tempranas ? "sí" : "no"],
      ["Alertas críticas autorizadas", d.alertas.criticas_autorizadas ? "sí" : "no"],
      ["Token de notificaciones guardado", d.token_de_notificaciones_guardado ? "sí (no se muestra)" : "no"],
    ])) : el("p", { textContent: "Ninguno." })));
    const f = data.familia;
    blocks.push(section("Círculo familiar", f ? table([["Círculo", f.circulo], ["Tu rol", f.rol], ["Tu alias", f.alias], ["Desde", f.desde], ["Integrantes", f.integrantes],
      ["Compartiendo ubicación ahora", f.ubicacion_compartida_ahora ? "sí" : "no"], ["Ubicación automática tras una alerta", f.ubicacion_automatica_activada ? "activada" : "desactivada"]]) : el("p", { textContent: "No perteneces a ningún círculo." })));
    const dev = data.desarrollador;
    blocks.push(section(`Claves de API (${dev.claves_de_api.length})`, dev.claves_de_api.length ? dev.claves_de_api.map((k) => table([["Nombre", k.name], ["Prefijo", k.prefix], ["Plan", k.plan], ["Estado", k.status], ["Creada", k.created_at], ["Último uso", k.last_used_at]])) : el("p", { textContent: "Ninguna." })));
    blocks.push(section(`Webhooks (${dev.webhooks.length})`, dev.webhooks.length ? dev.webhooks.map((w) => table([["Dirección", w.url], ["Estado", w.status], ["Creado", w.created_at]])) : el("p", { textContent: "Ninguno." })));
    blocks.push(section(`Reportes (${data.reportes.length})`, data.reportes.length ? data.reportes.map((r) => table(Object.entries(r).map(([k, v]) => [k, typeof v === "object" ? JSON.stringify(v) : v]))) : el("p", { textContent: "Ninguno." })));
    if (data.facturacion) blocks.push(section("Facturación", table([["Saldo", data.facturacion.saldo], ["Movimientos", data.facturacion.movimientos]])));
    blocks.push(el("p", { className: "account-meta", textContent: `Seismik no guarda: ${data.no_guardamos.join("; ")}.` }));
    $("data-detail").replaceChildren(...blocks);
    $("data-detail").hidden = false;
  }

  $("data-view").addEventListener("click", async () => {
    const detail = $("data-detail");
    if (!detail.hidden) { detail.hidden = true; $("data-view").textContent = "Ver el detalle"; return; }
    say($("data-status"), "Cargando tus datos…");
    try {
      renderDetail(await call("/data"));
      $("data-view").textContent = "Ocultar el detalle";
      say($("data-status"), "");
    } catch (error) { say($("data-status"), error.message, "error"); }
  });

  $("data-download").addEventListener("click", async () => {
    say($("data-status"), "Preparando la descarga…");
    try {
      const response = await fetch(`${API}/data?download=true`);
      if (!response.ok) throw new Error(`Error ${response.status}`);
      const url = URL.createObjectURL(await response.blob());
      const link = el("a", { href: url, download: "mis-datos-seismik.json" });
      document.body.append(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 10000);
      say($("data-status"), "Descarga lista.", "ok");
    } catch (error) { say($("data-status"), error.message, "error"); }
  });

  async function load(first = true) {
    try {
      const response = await fetch(`${API}/center`, { headers: { Accept: "application/json" } });
      if (response.status === 401) return show("out");
      if (!response.ok) throw new Error(`Error ${response.status}`);
      center = await response.json();
    } catch {
      $("loading").textContent = "No pudimos cargar tu cuenta. Recarga la página en un momento.";
      return;
    }
    $("who-name").textContent = center.name || "Sin nombre";
    $("who-email").textContent = center.email ? ` · ${center.email}` : "";
    $("who-id").textContent = center.account_id;
    $("reauth").hidden = center.recent_login;
    $("data-summary").textContent = countText(center.data);
    renderMethods();
    renderDeleteList();
    if (first) show("in");
  }

  const code = new URLSearchParams(location.search).get("link");
  if (code && NOTICES[code]) {
    notice(...NOTICES[code]);
    history.replaceState(null, "", location.pathname);
  }
  load();
})();
