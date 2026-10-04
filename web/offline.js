// No recarga automáticamente ni abandona la página durante una emergencia.
function updateConnection() {
  const offline = !navigator.onLine || document.body.dataset.connection === "offline";
  document.getElementById("connection-label").textContent = offline ? "Sin conexión a internet" : "Servicio temporalmente no disponible";
  document.getElementById("connection-title").textContent = offline ? "Sin señal. Seguimos contigo." : "Hagamos una pausa. Volveremos a conectar.";
  document.getElementById("connection-description").textContent = offline
    ? "Seismik no puede conectarse a internet. Revisa tu Wi-Fi o tus datos móviles y vuelve a intentar cuando tengas señal."
    : "Tu navegador detecta conexión, pero no pudimos cargar esta página. Vuelve a intentar o consulta el estado del servicio.";
  document.getElementById("connection-note").textContent = offline
    ? "Esta página está disponible sin conexión. El estado del servicio necesita internet."
    : "La conexión del navegador no garantiza que Seismik esté disponible.";
}
const retry = document.getElementById("retry");
const current = new URL(window.location.href);
// Conserva la ruta fallida, sin permitir redirecciones a otros dominios.
retry.href = current.pathname === "/offline.html" ? "/" : current.pathname + current.search;
retry.addEventListener("click", (event) => {
  if (!navigator.onLine) {
    event.preventDefault();
    document.getElementById("connection-note").textContent = "Todavía no hay conexión. Revisa tu Wi-Fi o tus datos móviles.";
  }
});
window.addEventListener("online", () => {
  delete document.body.dataset.connection;
  updateConnection();
});
window.addEventListener("offline", updateConnection);
updateConnection();
