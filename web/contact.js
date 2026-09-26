(() => {
  const form = document.querySelector("#contact-form");
  if (!form) return;

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!form.reportValidity()) return;

    const data = new FormData(form);
    const topic = data.get("topic");
    const body = [
      `Nombre: ${data.get("name")}`,
      `Correo: ${data.get("email")}`,
      "",
      String(data.get("message")).trim(),
    ].join("\n");
    window.location.href = `mailto:support@seismik.org?subject=${encodeURIComponent(`[${topic}] Contacto desde seismik.org`)}&body=${encodeURIComponent(body)}`;
  });
})();
