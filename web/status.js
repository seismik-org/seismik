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

document.getElementById("refresh").addEventListener("click", refreshStatus);
refreshStatus();
setInterval(refreshStatus, 60_000);
