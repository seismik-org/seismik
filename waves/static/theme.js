// Apariencia automática: sigue el esquema de color del dispositivo. Ya no hay selector ni preferencia guardada.
(() => {
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  const apply = () => { document.documentElement.dataset.theme = media.matches ? "dark" : "light"; };
  apply();
  media.addEventListener("change", apply);
})();
