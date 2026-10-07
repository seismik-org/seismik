const stateNames = { api: "api-state", web: "web-state", developers: "developers-state" };

function setState(service, healthy) {
  const element = document.getElementById(stateNames[service]);
  element.className = `state ${healthy ? "ok" : "degraded"}`;
  element.textContent = healthy ? "Operativo" : "Degradado";
}

async function refreshStatus() {
  const button = document.getElementById("refresh");
  button.disabled = true;
  try {
    const response = await fetch("/api/status", { cache: "no-store" });
    if (!response.ok) throw new Error(`status ${response.status}`);
    const status = await response.json();
    for (const [service, healthy] of Object.entries(status.services)) setState(service, healthy);
    const allHealthy = Object.values(status.services).every(Boolean);
    document.querySelector(".status-dot").className = `status-dot ${allHealthy ? "ok" : "degraded"}`;
    document.getElementById("overall-status").textContent = allHealthy ? "Todos los servicios públicos están operativos" : "Hay servicios públicos degradados";
    document.getElementById("checked-at").textContent = `Comprobado ${new Date(status.checked_at).toLocaleString("es-CO")}. Actualización automática cada 60 segundos.`;
  } catch {
    for (const service of Object.keys(stateNames)) setState(service, false);
    document.querySelector(".status-dot").className = "status-dot degraded";
    document.getElementById("overall-status").textContent = "No fue posible comprobar los servicios";
    document.getElementById("checked-at").textContent = "Intenta actualizar en unos minutos.";
  } finally { button.disabled = false; }
}

const serviceLabels = { api: "API pública", web: "Sitio web", developers: "Portal de desarrolladores" };

async function refreshHistory() {
  const container = document.getElementById("history");
  try {
    const response = await fetch("/api/history", { cache: "no-store" });
    if (!response.ok) throw new Error("history unavailable");
    const history = await response.json();
    if (!history.available) throw new Error("history unavailable");
    const fragment = document.createDocumentFragment();
    for (const [service, label] of Object.entries(serviceLabels)) {
      const article = document.createElement("article");
      article.className = "history-service";
      const title = document.createElement("h3");
      title.textContent = label;
      const bars = document.createElement("div");
      bars.className = "history-bars";
      let healthy = 0, failed = 0;
      for (const day of history.days) {
        const counts = day.services[service];
        healthy += counts.healthy;
        failed += counts.failed;
        const bar = document.createElement("button");
        bar.type = "button";
        bar.className = `history-day ${day.samples ? (counts.failed ? "degraded" : "ok") : "unknown"}`;
        const details = `${day.date}: ${day.samples ? `${counts.failed} comprobaciones fallidas de ${day.samples}` : "sin registros"}`;
        bar.title = details;
        bar.setAttribute("aria-label", details);
        bar.addEventListener("click", () => { summary.textContent = details; });
        bars.append(bar);
      }
      const summary = document.createElement("p");
      summary.className = "fine-print";
      const samples = healthy + failed;
      summary.textContent = samples ? `${(100 * healthy / samples).toLocaleString("es-CO", { maximumFractionDigits: 2 })}% de comprobaciones exitosas · ${failed} fallidas de ${samples}. Selecciona un día para ver el detalle.` : "Todavía no hay comprobaciones registradas.";
      article.append(title, bars, summary);
      fragment.append(article);
    }
    container.replaceChildren(fragment);
  } catch {
    container.textContent = "No fue posible cargar el historial. Intenta actualizar en unos minutos.";
  }
}

document.getElementById("refresh").addEventListener("click", () => { refreshStatus(); refreshHistory(); });
refreshStatus();
refreshHistory();
setInterval(() => { refreshStatus(); refreshHistory(); }, 60_000);
