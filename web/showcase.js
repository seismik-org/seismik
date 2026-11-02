// "Así se ve Seismik": prueba en vivo de la API pública, sin clave ni sesión.
// El worker de Cloudflare enruta seismik.org/v1/* hacia la API -igual que ya
// hace en devs.seismik.org-, así que una ruta relativa basta.
(() => {
  const list = document.querySelector("#showcase-list");
  const status = document.querySelector("#showcase-status");
  if (!list || !status) return;

  const magnitudeBand = (magnitude) => {
    if (magnitude >= 7) return "mmi-8";
    if (magnitude >= 6) return "mmi-6";
    if (magnitude >= 5) return "mmi-4";
    return "mmi-3";
  };

  const relativeTime = (isoString) => {
    const date = new Date(isoString);
    if (Number.isNaN(date.getTime())) return "";
    const seconds = Math.round((Date.now() - date.getTime()) / 1000);
    const units = [
      ["año", 31536000],
      ["mes", 2592000],
      ["día", 86400],
      ["hora", 3600],
      ["minuto", 60],
    ];
    for (const [unit, secondsInUnit] of units) {
      const value = Math.floor(seconds / secondsInUnit);
      if (value >= 1) return `hace ${value} ${unit}${value === 1 ? "" : unit === "mes" ? "es" : "s"}`;
    }
    return "hace instantes";
  };

  const magnitudeLabel = (event) => {
    const value = typeof event.magnitude === "number" ? event.magnitude.toFixed(1) : "—";
    return event.magnitude_type ? `${value} ${event.magnitude_type}` : value;
  };

  const officialURL = (value) => {
    try {
      const url = new URL(value);
      return url.protocol === "https:" && !url.username && !url.password ? url.href : null;
    } catch (_) { return null; }
  };

  function card(event) {
    const item = document.createElement("li");
    item.className = "showcase-card";

    const badge = document.createElement("span");
    item.append(badge);

    const body = document.createElement("div");
    body.className = "showcase-body";

    const place = document.createElement("p");
    place.className = "showcase-place";
    body.append(place);

    const meta = document.createElement("p");
    meta.className = "showcase-meta";
    body.append(meta);

    const reports = Array.isArray(event.source_reports)
      ? event.source_reports.filter(report => report && typeof report === "object") : [];
    if (!reports.length) reports.push(event);
    if (reports.length > 1) {
      const label = document.createElement("label");
      label.className = "showcase-agency";
      const caption = document.createElement("span");
      caption.textContent = `Agencia · ${reports.length} fuentes`;
      const select = document.createElement("select");
      select.setAttribute("aria-label", `Agencia del reporte: ${event.place || "sismo"}`);
      reports.forEach((report, index) => {
        const option = document.createElement("option");
        option.value = String(index);
        option.textContent = report.agency || "Agencia oficial";
        select.append(option);
      });
      select.addEventListener("change", () => {
        const selected = reports[Number(select.value)];
        if (selected) renderReport(selected);
      });
      label.append(caption, select);
      body.append(label);
    }

    const link = document.createElement("a");
    link.className = "showcase-link";
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = "Ver fuente oficial";
    body.append(link);

    // El formulario de ifeltit.seismik.org abre con este sismo ya elegido.
    const reportLink = document.createElement("a");
    reportLink.className = "showcase-link";
    reportLink.textContent = "¿Lo sentiste? Repórtalo";
    body.append(reportLink);

    function renderReport(report) {
      badge.className = `showcase-badge ${magnitudeBand(report.magnitude)}`;
      badge.textContent = magnitudeLabel(report);
      place.textContent = report.place || "Ubicación no especificada";
      const depth = Number.isFinite(report.depth_km) ? `${report.depth_km} km de profundidad` : "";
      meta.textContent = [report.agency, relativeTime(report.origin_time), depth].filter(Boolean).join(" · ");
      const date = new Date(report.origin_time);
      meta.title = Number.isNaN(date.getTime()) ? "" : date.toLocaleString("es-CO");
      const url = officialURL(report.official_url);
      link.hidden = !url;
      link.href = url || "";
      reportLink.hidden = !report.event_id;
      reportLink.href = report.event_id
        ? `https://ifeltit.seismik.org/?event=${encodeURIComponent(report.event_id)}` : "";
    }
    renderReport(reports[0]);

    item.append(body);
    return item;
  }

  async function load() {
    try {
      const response = await fetch("/v1/public/showcase-events");
      if (!response.ok) throw new Error(`Error ${response.status}`);
      const data = await response.json();
      const events = Array.isArray(data.events) ? data.events : [];

      list.replaceChildren();
      if (events.length === 0) {
        status.textContent = "Sin sismos de esta magnitud reportados por ahora.";
        return;
      }
      for (const event of events) list.append(card(event));
      status.textContent = "";
    } catch (_error) {
      list.replaceChildren();
      status.textContent = "No se pudo cargar el panel en vivo. La API sigue disponible en devs.seismik.org.";
    }
  }

  load();
})();
