# Build 64 — Modo de emergencia sin conexión

Incluye `c8cbb02`: epicentros locales y conectividad adaptativa, más pantalla
offline accesible desde Monitor y Configuración sin autenticación.

Guía de seguridad incluida en el binario, con fuente CDC accesible y aviso de
independencia; copia del historial con fecha explícita; notas/punto de encuentro
locales de hasta 1000 caracteres; indicador de reportes pendientes no entregados;
opción persistente para posponer historial y reportes y sincronización manual.
No corta Internet ni desactiva push, sensores autorizados o el registro seguro.

Android encola reportes antes de llamar a HTTP cuando se activa el modo. iOS
encola el cuerpo exacto antes de registrar o enviar y devuelve `queued`, nunca
`sent`. La sincronización automática respeta la opción; la acción «Buscar
conexión» la desactiva expresamente antes de intentar enviar.

iOS restaura eventos y fecha local inmediatamente, antes de esperar a la red.
No se conservan nuevas ubicaciones familiares ni se presenta a nadie como a
salvo a partir de datos antiguos. Notas locales no se envían a Seismik ni a la
familia automáticamente; pueden estar incluidas en respaldos del sistema.
No hay mapas descargables ni comunicación SMS/radio/satélite en este build.

Fuente de la guía: https://www.cdc.gov/earthquakes/safety/index.html
El modo no confirma sismos ni predice nuevos eventos offline. Sin transporte
disponible los reportes permanecen pendientes y no llegan a destinatarios.

Pruebas nuevas: persistencia de modo/notas, apertura sin sesión/red/caché y
encolado con cero llamadas HTTP. Mantiene `report_id` y las políticas previas de
consentimiento, caducidad, límite e idempotencia de las colas.

Distribución prevista: Play prueba interna existente y TestFlight, con
Critical Alerts aprobado. No promoción de producción. Verificar CI nativa de
iOS antes de disparar el workflow firmado y confirmar por separado procesamiento
de Apple y disponibilidad en Play.
