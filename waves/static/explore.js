import {downloadRecord} from "/assets/download.js";
const $ = id => document.getElementById(id);
const COMPONENT = {Z: "Vertical", N: "Norte-Sur", E: "Este-Oeste", 1: "Horizontal 1", 2: "Horizontal 2"};
const GROUP_LABELS = {evaluation: "Evaluación de magnitud", historical: "Históricos de referencia", cases: "Casos de estudio", fixtures: "Pruebas de reproducción"};
let data, plots = [], hover = null, T0 = 0, T1 = 1;

const fmt = new Intl.NumberFormat("es-CO");
const when = iso => iso ? iso.replace("T", " ").replace("Z", " UTC").replace(/\.\d+/, "") : "—";
const clock = ms => new Date(ms).toISOString().slice(11, 19);
const span = seconds => seconds >= 120 ? `${(seconds / 60).toFixed(1)} min` : `${seconds.toFixed(1)} s`;
const colors = () => { const s = getComputedStyle(document.documentElement); const pick = n => s.getPropertyValue(n).trim();
  return {text: pick("--text") || "#eef3ff", muted: pick("--muted") || "#9dadc8", line: pick("--line") || "#233249",
    channel: {Z: pick("--blue") || "#7cc4ff", N: "#2fae8c", E: "#d98a4e", 1: "#2fae8c", 2: "#d98a4e"}}; };

function el(tag, text, className) { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (className) node.className = className; return node; }
function fact(label, value) { const box = el("div"); box.append(el("dt", label), el("dd", value)); return box; }
function card(label, value, note, href) {
  const box = el("div"); box.append(el("span", label, "k"));
  const strong = el("strong"); if (href) { const a = el("a", value); a.href = href; a.rel = "noopener noreferrer"; a.target = "_blank"; strong.append(a); } else strong.textContent = value;
  box.append(strong); if (note) box.append(el("small", note)); return box;
}
async function api(path) {
  const response = await fetch(path, {cache: "no-store", credentials: "same-origin"});
  const result = await response.json().catch(() => ({}));
  if (!response.ok) { const error = new Error(result.detail || "No se pudo consultar Waves."); error.status = response.status; throw error; }
  return result;
}
function gate(text) { $("state").hidden = true; $("viewer").hidden = true; $("gate").hidden = false; $("gate-text").textContent = text; }

function trace_time(trace, bucket) { return Date.parse(trace.start) + (bucket + 0.5) * (trace.duration_s * 1000) / data.buckets; }
function stationTraces(station) { return data.traces.filter(t => `${t.network}.${t.station}` === station); }

function scaleFor(trace, group) {
  const mode = $("scale").value;
  const peak = list => Math.max(1, ...list.map(t => Math.max(Math.abs(Math.min(...t.mins)), Math.abs(Math.max(...t.maxs)))));
  return mode === "all" ? peak(data.traces) : mode === "station" ? peak(group) : peak([trace]);
}

function draw(plot) {
  const {canvas, trace, scale} = plot, ratio = window.devicePixelRatio || 1, palette = colors();
  const width = canvas.clientWidth, height = canvas.clientHeight;
  canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
  const g = canvas.getContext("2d"); g.setTransform(ratio, 0, 0, ratio, 0, 0); g.clearRect(0, 0, width, height);
  const mid = height / 2, k = (mid - 6) / scale, left = 0, usable = width;
  const x = ms => left + (ms - T0) / (T1 - T0) * usable;
  g.strokeStyle = palette.line; g.lineWidth = 1; g.beginPath(); g.moveTo(0, mid + .5); g.lineTo(width, mid + .5); g.stroke();
  const origin = data.context.origin_time && Date.parse(data.context.origin_time);
  if (origin && origin >= T0 && origin <= T1) {
    g.setLineDash([4, 4]); g.strokeStyle = palette.muted; g.beginPath(); g.moveTo(x(origin) + .5, 0); g.lineTo(x(origin) + .5, height); g.stroke(); g.setLineDash([]);
  }
  g.strokeStyle = palette.channel[trace.channel.slice(-1)] || palette.text; g.lineWidth = 1;
  g.beginPath();
  for (let i = 0; i < data.buckets; i++) {
    const px = Math.round(x(trace_time(trace, i))) + .5;
    g.moveTo(px, mid - trace.maxs[i] * k); g.lineTo(px, mid - trace.mins[i] * k - 1);
  }
  g.stroke();
  if (hover !== null) { g.strokeStyle = palette.text; g.globalAlpha = .55; g.beginPath(); g.moveTo(hover + .5, 0); g.lineTo(hover + .5, height); g.stroke(); g.globalAlpha = 1; }
}
function drawAxis(canvas) {
  const ratio = window.devicePixelRatio || 1, palette = colors(), width = canvas.clientWidth, height = canvas.clientHeight;
  canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
  const g = canvas.getContext("2d"); g.setTransform(ratio, 0, 0, ratio, 0, 0); g.clearRect(0, 0, width, height);
  g.fillStyle = palette.muted; g.strokeStyle = palette.line; g.font = "11px ui-monospace, monospace"; g.textBaseline = "top";
  const total = (T1 - T0) / 1000, step = [5, 10, 20, 30, 60, 120, 300].find(s => total / s <= Math.max(4, width / 90)) || 600;
  for (let s = 0; s <= total; s += step) {
    const px = Math.round(s / total * width) + .5;
    g.beginPath(); g.moveTo(px, 0); g.lineTo(px, 6); g.stroke();
    const label = clock(T0 + s * 1000); g.textAlign = px < 30 ? "left" : px > width - 30 ? "right" : "center"; g.fillText(label, px, 9);
  }
}

function build() {
  const station = $("station").value, area = $("plots"); area.replaceChildren(); plots = [];
  const group = station === "*" ? data.traces.filter(t => t.channel.endsWith("Z")) : stationTraces(station);
  const traces = group.length ? group : data.traces;
  T0 = Math.min(...data.traces.map(t => Date.parse(t.start))); T1 = Math.max(...data.traces.map(t => Date.parse(t.end)));
  for (const trace of traces) {
    const box = el("div", undefined, "plot"); const canvas = el("canvas");
    canvas.setAttribute("role", "img"); canvas.setAttribute("aria-label", `Forma de onda de ${trace.id}`);
    const comp = trace.channel.slice(-1);
    box.append(canvas, el("span", `${trace.id} · ${COMPONENT[comp] || comp}`, "tag"), el("span", `pico ${fmt.format(trace.peak_counts)} cuentas`, "peak"));
    area.append(box);
    const plot = {canvas, trace, scale: scaleFor(trace, traces)}; plots.push(plot);
    canvas.addEventListener("pointermove", event => onMove(event, canvas));
    canvas.addEventListener("pointerleave", () => { hover = null; redraw(); $("readout").textContent = "Pasa el cursor sobre una onda para leer el tiempo y la amplitud."; });
  }
  const axis = el("div", undefined, "plot axis"); const axisCanvas = el("canvas"); axis.append(axisCanvas); area.append(axis); plots.axis = axisCanvas;
  redraw();
}
function redraw() { for (const plot of plots) draw(plot); if (plots.axis) drawAxis(plots.axis); }

function onMove(event, canvas) {
  const rect = canvas.getBoundingClientRect(), px = event.clientX - rect.left;
  hover = Math.round(px);
  redraw();
  const ms = T0 + px / rect.width * (T1 - T0);
  const lines = plots.map(({trace}) => {
    const bucket = Math.floor((ms - Date.parse(trace.start)) / (trace.duration_s * 1000) * data.buckets);
    return bucket >= 0 && bucket < data.buckets ? `${trace.channel}: ${fmt.format(trace.mins[bucket])}…${fmt.format(trace.maxs[bucket])}` : null;
  }).filter(Boolean);
  const origin = data.context.origin_time && Date.parse(data.context.origin_time);
  const rel = origin ? ` (${((ms - origin) / 1000 >= 0 ? "+" : "") + ((ms - origin) / 1000).toFixed(1)} s del origen de referencia)` : "";
  $("readout").textContent = `${clock(ms)} UTC${rel} · cuentas mín…máx · ${lines.join(" · ")}`;
}

function render() {
  const {context, record} = data, c = context;
  $("kicker").textContent = ({evento: "SISMO", ruido: "VENTANA DE RUIDO", caso: "CASO DE ESTUDIO"})[c.kind] || "GRABACIÓN";
  $("title").textContent = c.title; document.title = `${c.title} · Waves · Seismik`;
  const box = $("context"); box.replaceChildren();
  if (c.origin_time) box.append(card("Origen (referencia)", when(c.origin_time), c.reference ? `Según ${c.reference}` : ""));
  if (typeof c.magnitude === "number") box.append(card("Magnitud", `${c.magnitude.toFixed(1)}${c.magnitude_type ? ` ${c.magnitude_type}` : ""}`, c.detail && c.kind === "evento" ? c.detail : "", c.reference_url || undefined));
  if (typeof c.depth_km === "number") box.append(card("Profundidad", `${c.depth_km.toFixed(0)} km`));
  if (typeof c.latitude === "number") box.append(card("Epicentro", `${c.latitude.toFixed(2)}°, ${c.longitude.toFixed(2)}°`));
  if (c.place && c.place !== c.title) box.append(card("Lugar", c.place));
  const stations = [...new Set(data.traces.map(t => `${t.network}.${t.station}`))];
  box.append(card("Registro", `${stations.length} estaciones · ${data.traces.length} canales`, `${data.traces[0].rate} muestras/s · ${span(Math.max(...data.traces.map(t => t.duration_s)))}`));
  if (c.kind !== "evento" || !c.origin_time) box.append(card("Qué es", c.kind === "ruido" ? "Sin sismo" : "Registro histórico", c.detail));
  const select = $("station"); select.replaceChildren(...stations.map(s => { const o = el("option", s); o.value = s; return o; }));
  if (stations.length > 1) { const all = el("option", "Todas · componente vertical"); all.value = "*"; select.prepend(all); select.value = "*"; }
  const body = $("channels"); body.replaceChildren();
  for (const t of data.traces) {
    const tr = el("tr"); for (const value of [`${t.id}`, `${t.rate} Hz`, when(t.start), span(t.duration_s), fmt.format(t.samples), `${fmt.format(t.peak_counts)}`, `${fmt.format(t.rms_counts)}`]) tr.append(el("td", value));
    body.append(tr);
  }
  const file = $("file"); file.replaceChildren(
    fact("Archivo", record.name), fact("Conjunto", GROUP_LABELS[record.group] ?? record.category), fact("Formato", `${record.format} · ${(record.bytes / 1e6).toFixed(2)} MB`),
    fact("SHA-256", record.sha256), fact("Estado", "Material de investigación, sin validación científica independiente."),
    fact("Redistribución", "Requiere revisar las condiciones de la fuente de datos."));
  const button = $("download"); button.hidden = data.downloads_enabled !== true;
  if (!button.hidden) button.onclick = () => downloadRecord(record.id, button, (text, error) => { $("download-status").textContent = text; $("download-status").dataset.state = error ? "error" : "ok"; });
  $("state").hidden = true; $("viewer").hidden = false; build();
}

async function initialize() {
  const id = new URLSearchParams(location.search).get("id") || "";
  if (!/^[0-9a-f]{24}$/.test(id)) { gate("Elige una grabación en el catálogo para ver sus ondas."); return; }
  try { data = await api(`/v1/waves/records/${id}/preview`); }
  catch (error) {
    if (error.status === 401) gate("Inicia sesión con tu cuenta Seismik para ver esta grabación.");
    else if (error.status === 403) gate("Tu cuenta aún no está autorizada para el piloto. Solicita acceso por correo a support@seismik.org.");
    else if (error.status === 404) gate("No encontramos esa grabación en el catálogo.");
    else { $("state").textContent = error.message; }
    return;
  }
  $("station").addEventListener("change", build); $("scale").addEventListener("change", build);
  window.addEventListener("resize", redraw);
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => setTimeout(redraw, 50));
  render();
}
initialize();
