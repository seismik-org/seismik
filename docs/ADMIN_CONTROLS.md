# Controles de operación

La pestaña Controles de admin.seismik.org permite pausar y reanudar alertas
sísmicas a dispositivos y publicaciones automáticas en X o Facebook. No cambia
las credenciales, el modo de pruebas ni los permisos de los servicios.

Las pausas se guardan sin expiración en Redis (`seismik:operations:paused`) y
se consultan antes de cada envío. Se conservan al reiniciar API y workers.
Un envío ya iniciado puede terminar. Las alertas familiares, el catálogo y los
webhooks siguen funcionando. Los eventos procesados y omitidos durante la pausa
no se reenvían al reanudar.

Cada worker anuncia cada 30 segundos si la función está configurada para envíos;
el anuncio expira a los 90 segundos. La API no permite reanudar una función sin
un anuncio vigente y configuración habilitada. Configurar Facebook sigue
requiriendo sus variables y credenciales en Cloud Run/Secret Manager. El panel
nunca recibe esos secretos ni convierte un servicio de prueba en producción.

GET /v1/admin/controls consulta los estados. PUT /v1/admin/controls/{alerts,x,facebook}
recibe únicamente `{"enabled": false}` para pausar o `{"enabled": true}` para
reanudar. Ambos exigen la cuenta autorizada y el borde de admin; los cambios
exigen además Origin del panel y X-Seismik-Admin: 1. La pausa y su registro de
auditoría se escriben en una transacción de Redis.

Desplegar API, web y el servicio combinado seismik-dispatcher. Antes de comprobar
los estados, esperar el primer anuncio de los workers. Verificar las pausas con
Redis y envíos simulados en local; no pausar alertas de producción como prueba.

Registros incluye los streams reales `stream:seismik:x-audit` y
`stream:seismik:facebook-audit`. Las entradas antiguas con valores JSON no finitos
se muestran con null; se conserva la redacción de secretos e IP. La interfaz
descarta respuestas de una selección anterior y permite reintentar errores sin
recargar la página.
