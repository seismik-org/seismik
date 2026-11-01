// Descarga el MiniSEED original completo. Va por fetch para poder mostrar un mensaje claro si falla; el archivo
// nunca pasa por la página más allá de entregárselo al navegador como descarga.
export async function downloadRecord(id, button, status, resource = false) {
  const label = button.textContent;
  button.disabled = true; button.textContent = "Preparando…"; status("");
  try {
    const response = await fetch(`/v1/waves/${resource ? "resources" : "records"}/${encodeURIComponent(id)}/download`, {cache: "no-store", credentials: "same-origin"});
    if (!response.ok) {
      const detail = (await response.json().catch(() => ({}))).detail;
      throw new Error(typeof detail === "string" ? detail : "No se pudo descargar la grabación.");
    }
    const name = /filename="([^"]+)"/.exec(response.headers.get("content-disposition") ?? "")?.[1] ?? `${id}.mseed`;
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url; link.download = name; document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
    status(`Descargado ${name}. Verifica su huella SHA-256 con la que aparece en el catálogo.`);
  } catch (error) { status(error.message, true); }
  finally { button.disabled = false; button.textContent = label; }
}
