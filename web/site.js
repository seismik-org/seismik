// El menú móvil es un <details>: funciona sin JavaScript, pero sin esto queda
// abierto encima del contenido después de saltar a una sección.
for (const menu of document.querySelectorAll(".mobile-menu")) {
  menu.addEventListener("click", (event) => {
    if (event.target.closest("a")) menu.open = false;
  });
  document.addEventListener("click", (event) => {
    if (menu.open && !menu.contains(event.target)) menu.open = false;
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && menu.open) {
      menu.open = false;
      menu.querySelector("summary")?.focus();
    }
  });
}
