# Página del Grupo Seismik

La página vive en `web/grupo/index.html` y utiliza los estilos compartidos del
portal más `web/grupo/group.css`. Se enlaza desde el pie de la portada y el
sitemap en `https://seismik.org/grupo/`, su dirección canónica.

Los cambios de `web/` activan el despliegue web existente de GitHub Actions
cuando llegan a `main` y pasan sus comprobaciones. No requieren cambios en la
API, los servicios de notificaciones ni las aplicaciones móviles.

## Subdominio

`deploy/cloudflare-edge-router.js` también traduce la raíz de
`group.seismik.org` a `/grupo/` en el origen web. Mantiene las rutas de los
recursos compartidos y no sustituye la portada sísmica de `seismik.org`.

Como el enrutador no se publica desde el workflow actual, la activación del
subdominio requiere publicar ese Worker con su configuración y secretos
existentes. También requiere un registro DNS proxied de `group.seismik.org`
y que la ruta del Worker cubra ese hostname (por ejemplo, la ruta existente
`*.seismik.org/*`). No cambies los bindings ni el secreto de origen.

El commit de la página y un despliegue web correcto no confirman por sí solos
que el subdominio esté activo. Comprueba por separado que su raíz entregue la
página del grupo y que el CSS y el logotipo carguen correctamente.
