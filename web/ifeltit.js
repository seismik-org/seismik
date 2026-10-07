"use strict";
const form = document.querySelector("#report-form");
const status = document.querySelector("#status");
const steps = [...form.querySelectorAll("[data-step]")];
const control = (name) => form.elements.namedItem(name);
let step = 0, config, widget, token = "", pending, busy = false, accuracy = null;
const now = new Date();
control("observed_at").value = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0,16);

function payload() {
  const data = new FormData(form);
  const report = {
    observed_at: new Date(data.get("observed_at")).toISOString(),
    country_code: data.get("country_code").toUpperCase(),
    latitude: Number(data.get("latitude")), longitude: Number(data.get("longitude")),
    location_precision: control("precise").checked ? "precise" : "approximate",
    location_accuracy_m: accuracy,
    felt: data.get("felt") === "true",
    intensity_mmi: data.get("felt") === "true" ? Number(data.get("intensity_mmi")) : null,
    share_with_official_agencies: control("share_with_official_agencies").checked,
  };
  for (const name of ["duration_seconds", "building_height", "floor"]) {
    if (data.get(name) !== "") report[name] = Number(data.get(name));
  }
  for (const name of ["movement", "activity", "building_type", "reaction", "others_felt", "noise", "windows", "lamps", "furniture"]) {
    if (data.get(name)) report[name] = data.get(name);
  }
  return report;
}
function review() {
  const summary = document.querySelector("#summary");
  summary.replaceChildren();
  for (const element of form.querySelectorAll("input, select")) {
    if (!element.name || element.type === "checkbox" || !element.value || element.closest("#intensity-label")?.hidden) continue;
    const dt = document.createElement("dt"), dd = document.createElement("dd");
    dt.textContent = element.closest("label").firstChild.textContent.trim();
    dd.textContent = element.tagName === "SELECT" ? element.selectedOptions[0].textContent : element.value;
    summary.append(dt,dd);
  }
  const dt = document.createElement("dt"), dd = document.createElement("dd");
  dt.textContent = "Ubicación almacenada";
  dd.textContent = control("precise").checked ? "Exacta, por tu elección" : `${Number(control("latitude").value).toFixed(2)}, ${Number(control("longitude").value).toFixed(2)} (aproximada)`;
  summary.append(dt,dd);
}
function showStep(index) {
  step = index;
  steps.forEach((el,i) => el.hidden = i !== step);
  document.querySelectorAll(".steps li").forEach((el,i) => {
    if (i === step) el.setAttribute("aria-current","step"); else el.removeAttribute("aria-current");
  });
  document.querySelector("#back").hidden = step === 0;
  document.querySelector("#next").hidden = step === 2;
  document.querySelector("#send").hidden = step !== 2;
  if (step === 2) { review(); loadConfig().catch(error => { status.textContent = error.message; }); }
}
function valid(index) {
  for (const el of steps[index].querySelectorAll("input,select")) {
    if (!el.checkValidity()) { el.reportValidity(); return false; }
  }
  return true;
}
form.addEventListener("input", (event) => {
  pending = undefined;
  if (["latitude","longitude"].includes(event.target.name)) accuracy = null;
  const felt = control("felt").value === "true";
  document.querySelector("#intensity-label").hidden = !felt;
  control("intensity_mmi").required = felt;
  if (!felt) control("intensity_mmi").value = "";
});
document.querySelector("#next").addEventListener("click", () => { if (valid(step)) showStep(step+1); });
document.querySelector("#back").addEventListener("click", () => showStep(step-1));
document.querySelector("#locate").addEventListener("click", () => {
  const message = document.querySelector("#location-status");
  if (!navigator.geolocation) { message.textContent = "Geolocalización no disponible. Escribe las coordenadas."; return; }
  message.textContent = "Buscando ubicación…";
  navigator.geolocation.getCurrentPosition(({coords}) => {
    if (busy) return;
    control("latitude").value = coords.latitude;
    control("longitude").value = coords.longitude;
    accuracy = coords.accuracy; pending = undefined;
    message.textContent = "Ubicación lista. Revisa las coordenadas antes de continuar.";
    if (step === 2) review();
  }, () => { message.textContent = "No pudimos obtener tu ubicación. Puedes escribir las coordenadas."; }, {timeout:10000, maximumAge:60000});
});
async function loadConfig() {
  const response = await fetch("/v1/reports/web/config", {cache:"no-store", signal:AbortSignal.timeout(10000)});
  if (!response.ok) throw new Error("No se pudo cargar la configuración. Intenta enviar de nuevo.");
  config = await response.json();
  if (!config.enabled) throw new Error("El envío aún no está habilitado. Inténtalo más tarde.");
  if (!config.turnstile_required || step !== 2) return;
  if (!window.turnstile) await new Promise((resolve,reject) => {
    const script = document.createElement("script");
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
    token = ""; if (widget !== undefined) window.turnstile.reset(widget);
  }
});
document.querySelector("#another").addEventListener("click", () => window.location.reload());
loadConfig().catch(error => { status.textContent = error.message; });
