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

  function card(event) {
    const item = document.createElement("li");
    item.className = "showcase-card";

    const badge = document.createElement("span");
    badge.className = `showcase-badge ${magnitudeBand(event.magnitude)}`;
    badge.textContent = magnitudeLabel(event);
    item.append(badge);

    const body = document.createElement("div");
    body.className = "showcase-body";

    const place = document.createElement("p");
    place.className = "showcase-place";
    place.textContent = event.place || "Ubicación no especificada";
    body.append(place);

    const meta = document.createElement("p");
    meta.className = "showcase-meta";
    meta.textContent = [event.agency, relativeTime(event.origin_time)].filter(Boolean).join(" · ");
    body.append(meta);

    if (event.official_url) {
      const link = document.createElement("a");
      link.className = "showcase-link";
      link.href = event.official_url;
      link.target = "_blank";
      link.rel = "noopener";
      link.textContent = "Ver fuente oficial";
      body.append(link);
    }

    // El formulario de ifeltit.seismik.org abre con este sismo ya elegido.
    if (event.event_id) {
      const report = document.createElement("a");
      report.className = "showcase-link";
      report.href = `https://ifeltit.seismik.org/?event=${encodeURIComponent(event.event_id)}`;
      report.textContent = "¿Lo sentiste? Repórtalo";
      body.append(report);
    }

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
