(async () => {
  const buttons = [...document.querySelectorAll("[data-provider]")];
  const availability = document.querySelector("#availability");
  try {
    const response = await fetch("/v1/oauth/providers", { credentials: "include" });
    if (!response.ok) throw new Error("No se pudo consultar los proveedores");
    const { providers } = await response.json();
    let available = 0;
    for (const button of buttons) {
      const enabled = Boolean(providers?.[button.dataset.provider]?.enabled);
      button.hidden = !enabled;
      available += Number(enabled);
    }
    if (!available) throw new Error("No hay un proveedor de acceso disponible");
  } catch (_) {
    for (const button of buttons) button.hidden = true;
    availability.textContent = "El acceso no está disponible temporalmente. Inténtalo de nuevo en unos minutos.";
    availability.hidden = false;
  }
  for (const button of buttons) {
    button.addEventListener("click", () => {
      window.location.assign(`/v1/oauth/login?provider=${encodeURIComponent(button.dataset.provider)}`);
    });
  }
})();
