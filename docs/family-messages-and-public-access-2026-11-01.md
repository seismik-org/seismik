# Familia y acceso público alternativo

## Mensajes de Familia

`POST /v1/family/messages` y `GET /v1/family/messages` exigen la sesión de la cuenta y pertenencia activa al círculo. Cada envío conserva su UUID en los reintentos y declara círculo y remitente público: el servidor contrasta ambos con la sesión, para no enviar un pendiente de otra cuenta o familia. El texto tiene un máximo de 280 caracteres. No admite adjuntos, coordenadas ni campos de estado de seguridad.

Los textos aceptados vencen en Redis en 24 horas. La lectura se limita a los 50 más recientes, con un máximo de 500 mensajes aceptados por círculo en 24 horas y 12 envíos nuevos por persona y minuto. El límite por círculo se comprueba dentro de la transacción para acotar también el texto almacenado, no sólo el índice; nunca impide usar los avisos de estado. `Cache-Control: no-store` protege las respuestas. La aceptación no acredita entrega ni lectura. No se envían a los streams de detección, integración, alertas críticas ni push; las apps consultan al abrir Familia y cada 30 segundos mientras la vista está activa. No se anuncia recepción instantánea en segundo plano.

Android y el iPhone nativo guardan la cola por cuenta y círculo en el almacén seguro del dispositivo. También conservan una lista de integrantes para volver a abrir Familia después de reiniciar sin conexión: esa lista excluye ubicaciones y estados antiguos. Fallos de conexión conservan el UUID y el texto. Los pendientes de más de 24 horas no se transmiten: permanecen visibles para revisar o cancelar. Se admiten hasta 50 pendientes, sin descartar los anteriores al llenarse. Las respuestas rápidas incluyen avisos de punto de encuentro y dificultad para llamar. Un mensaje no marca a nadie como a salvo.

El botón SMS abre el compositor del sistema: la persona elige destinatario y confirma. No pide permisos de lectura/envío automático de SMS, no sincroniza conversaciones SMS y no puede enviar sin cobertura móvil. Puede generar cargos del operador. El chat de Seismik usa Internet y autenticación de cuenta; no es una implementación de SMS, WhatsApp, malla Bluetooth ni cifrado de extremo a extremo. Debe reflejarse el tratamiento de texto familiar en las declaraciones de privacidad de las tiendas antes de publicar una nueva versión.

## Continuidad pública

`deploy/continuity-wrapper.mjs` se renderiza como gateway independiente delante de los Workers existentes de Seismik, JADE y PortiPaq. Usa una vinculación de servicio al Worker original, conservando sus recursos y autenticación. Las rutas añadidas son sólo la portada, `/sw.js` y `/__continuity/*` de los hosts públicos. No reemplaza las rutas privadas.

Accesos de lectura:

- `https://seismik-access.todozhop.workers.dev/`
- `https://seismik-access.todozhop.workers.dev/liveahora/`
- `https://jade-access.todozhop.workers.dev/`
- `https://portipaq-access.todozhop.workers.dev/`

En estos hosts alternativos sólo se permite GET/HEAD de información pública y recursos estáticos. Se eliminan credenciales entrantes y cookies de respuesta, formularios y scripts. Se aplica `noindex`, CSP sin conexiones ni ejecución de scripts, y una advertencia visible de que no hay actualizaciones en vivo ni operaciones privadas. Los dominios alternativos no trasladan sesiones.

El service worker guarda una página informativa autocontenida y sólo la usa como respaldo de navegación a páginas públicas expresamente enumeradas. Nunca guarda respuestas de cuenta, API, administración o explorador. Requiere una visita previa con almacenamiento permitido. No puede corregir una primera resolución DNS fallida ni garantizar acceso si también se bloquea workers.dev, falla Cloudflare o no hay conectividad.

## Despliegue conservador

El sitio y la API se construyen como capas sobre las imágenes que ya estaban publicadas el 1 de noviembre, para conservar LiveAhora y otros cambios hechos desde el otro PC. El archivo `family.py` de esa imagen se comparó con la base local antes de modificarlo. Sólo se actualiza ese módulo en la API; el dispatcher y el detector permanecen intactos.

Las fuentes completas de LiveAhora de la imagen actual todavía no están integradas en esta rama: se preservan en la imagen base. No sustituir producción con una reconstrucción ciega de main. Los respaldos y comprobantes del despliegue se conservan localmente en `work/audits/family-web-20261101` y `work/deploy-family-web-20261101`.

Producción: `seismik-api-family-1101-bounded` (imagen `sha256:08b1ce567f356fbcb13976a27cdb44a43fff8d2b55f147cc71fe444c1fd63e47`) y `seismik-web-family-1101-final` (imagen `sha256:6ca819179126d0a5e2889ab205436e9f74cd2d961b15367b395c07ee441ab007`). Se comprobaron primero con etiquetas sin tráfico y se retiraron esas etiquetas al terminar. Reversión: API `seismik-api-liveahora-1031-r4`; web `seismik-web-liveahora-1031-r1`.

Los gateways `jade-access`, `portipaq-access` y `seismik-access` tienen como único binding su servicio `ORIGIN`. Las rutas añadidas y las versiones originales de los Workers están respaldadas en el informe local. Los Workers originales quedaron con su código original, sus bindings y assets conservados. Un primer intento de envolverlos directamente dio errores por el tipo MIME de los módulos y se revirtió; los gateways independientes se probaron después antes de enlazar las rutas públicas. El Worker temporal de comprobación se eliminó.
