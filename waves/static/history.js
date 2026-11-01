const list = document.getElementById("historical-list");
const status = document.getElementById("historical-status");
let items = [];
function node(tag, text, className) {
  const item = document.createElement(tag); item.textContent = text;
  if (className) item.className = className;
  return item;
}
function render() {
  const region = document.getElementById("historical-region").value;
  const matches = items.filter(item => !region || item.region === region);
  list.replaceChildren(...matches.map(item => {
    const card = node("article", "", "group historical-card");
    card.append(node("span", item.region === "colombia" ? "COLOMBIA" : "MUNDO", "eyebrow"),
      node("h3", item.title), node("strong", `M ${item.magnitude.toLocaleString("es-CO", {minimumFractionDigits: 1})}${item.magnitude_type ? ` ${item.magnitude_type}` : ""}`),
      node("p", `${item.date} · ${item.date_basis}`, "fine"), node("p", item.summary),
      node("p", item.lesson, "history-lesson"));
    const source = node("a", `${item.source} ↗`); source.href = item.source_url;
    source.target = "_blank"; source.rel = "noopener noreferrer";
    card.append(source, node("p", "Ficha documental · sin grabación vinculada en Waves", "fine"));
    return card;
  }));
  status.textContent = `${matches.length} referencias documentales. Magnitudes de las fuentes, no calculadas por Seismik.`;
}
async function initialize() {
  try {
    const response = await fetch("/assets/historical-earthquakes.json", {cache: "no-cache"});
    if (!response.ok) throw new Error();
    const data = await response.json(); items = data.items;
    document.getElementById("historical-notice").textContent = data.notice;
    document.getElementById("historical-region").addEventListener("change", render); render();
  } catch { status.textContent = "Las fichas no están disponibles. Consulta las fuentes SGC y USGS enlazadas abajo."; }
}
initialize();
