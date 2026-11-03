# Versión móvil 71 preparada — sin publicar

Decisión del usuario: dejar preparada la versión sin publicar todavía. La candidata Flutter es `1.0.0+71`, en `feature/family-chat-status-theme`. No se despliega la API nueva, no se cambia tráfico, no se publica en tiendas ni se actualiza la app instalada.

## Comportamiento

- Familia permite elegir el chat del círculo o una conversación privada con otro integrante activo. Conserva el chat grupal existente. El servidor verifica la sesión, remitente, círculo y destinatario; comprueba de nuevo la pertenencia dentro de la transacción antes de aceptar un envío. Una tercera persona no puede leer una conversación ajena ni suplantar al remitente.
- Los mensajes privados usan índices separados; nunca se insertan en el chat del grupo. La cola local se guarda en almacenamiento seguro por cuenta, círculo y destinatario. Cambiar de conversación no redirige pendientes. Una respuesta de una API anterior no se muestra como chat privado: se exige coincidencia explícita del destinatario.
- Sin red se conservan los pendientes, sin intentar enviarlos. Se mantienen UUID, vencimiento y cancelación recuperable ante fallos del almacenamiento. No se envían mensajes reales durante las pruebas.
- Al desactivar el color del sistema se usa una paleta neutra con acento turquesa, en claro y oscuro. Los colores dinámicos de Android y las escalas sísmicas se conservan.
- Tras fallos de conexión se consulta `https://status.seismik.org/api/status`, sin credenciales ni datos familiares. Se limita a seis segundos y se reutiliza el resultado durante 45 segundos. Sólo se acepta un estado reciente. Una caída confirmada, una conexión probablemente local y una causa desconocida tienen explicaciones distintas en español; un HTTP 5xx nunca se atribuye al teléfono. Errores de permisos, sesión y límites se traducen sin consultar el monitor.

## Límites y privacidad

280 caracteres; últimos 50 mensajes por conversación; conservación del servidor de 24 horas; máximo compartido de 500 mensajes por círculo en 24 horas y 12 envíos nuevos por miembro/minuto. Hasta 50 pendientes locales por conversación. Los pendientes vencidos requieren revisión y no se transmiten automáticamente. No se ofrece cifrado de extremo a extremo ni confirmación de lectura. Se consulta al abrir y cada 30 segundos mientras la vista está activa; no hay nuevas notificaciones push de mensajes. El botón SMS abre el compositor del sistema y requiere la acción de la persona.

El alcance móvil modificado es Flutter/Android. No se ha implementado esta ampliación en la app iPhone nativa. Antes de distribuir deben revisarse las declaraciones de privacidad de las tiendas y probarse dos cuentas reales en dispositivos; no se ha validado entrega real, Play Integrity ni actualización con firma original.

## API construida y retenida

Cloud Build `8e518af2-3b36-48fa-a54c-fb046cb16607`: SUCCESS.

Imagen preparada:
`us-east1-docker.pkg.dev/seismik-15bbb/seismik/api@sha256:3e6298ea059471c280b6c02f53951ca0696c895d31d0f48003125236b2e93744`

Etiqueta: `family-chat-v71-20261102`. Se construyó como capa que sustituye únicamente `/app/src/api/family.py`, con comprobación del hash anterior, compilación Python y permisos 0644. Base preservada:
`us-east1-docker.pkg.dev/seismik-15bbb/seismik/api@sha256:dcb243856af3f897bbf537e1ee44a55bcb4861644daedaed945e14dd633c2727`.

Los archivos de construcción y el respaldo privado de configuración están en Cloud Shell, `~/seismik-family-v71-20261102/`. No copiar el respaldo privado al repositorio. No se modificaron variables, secretos, IAM, DNS ni servicios de detección/dispatch. La revisión de API observada antes de construir fue `seismik-api-showcase-agencies-1102`, con el 100 % del tráfico. No se emitió ningún despliegue en este trabajo.

## Publicación posterior

1. Revisar que producción no haya cambiado desde la base anterior. Si cambió, reconstruir la capa sobre la nueva base preservando los cambios.
2. Con autorización para publicar, preparar una revisión API sin tráfico conservando su configuración y probar autenticación, chats de dos participantes y aislamiento de una tercera cuenta. Después migrar tráfico y conservar la revisión anterior para reversión.
3. Habilitar las cuatro variables originales `SEISMIK_KEYSTORE`, `SEISMIK_KEYSTORE_PASSWORD`, `SEISMIK_KEY_ALIAS`, `SEISMIK_KEY_PASSWORD` localmente, sin compartir sus valores. Compilar sin `seismikUnsignedReleaseCheck`. Verificar certificado y actualización conservando datos antes de subir a la pista de pruebas.
4. Distribuir la app sólo después de validar la API. No desinstalar la app existente ni sustituir la clave original.

La firma original se recuperó posteriormente desde la transferencia que el usuario puso en Drive. El JKS coincide byte por byte con el original preservado; la contraseña abre la entrada privada `seismik-upload` y quedó protegida mediante DPAPI para este usuario/PC en `%LOCALAPPDATA%\Seismik\signing`. No hay contraseñas ni claves en el repositorio. Las variables de firma se habilitan sólo durante cada compilación y se retiran después.

El certificado de carga comprobado tiene SHA256 `83:27:89:71:F1:D8:7C:3E:FC:CC:DD:17:98:D2:C6:5C:6D:F8:C1:20:BB:8E:2B:16:EA:42:17:E3:9E:F6:BE:E0`. Falta contrastarlo con Play Console y validar allí la actualización antes de distribuir. Recuperar la firma no modifica la decisión de no publicar todavía.

La opción Gradle existente `seismikUnsignedReleaseCheck=true` sólo comprueba una compilación release con firma de depuración; cualquier APK obtenido así NO es un artefacto distribuible ni una actualización de la app instalada. El AAB final `seismik-v71-firma-original.aab` se compiló con `flutter build appbundle --release --no-pub`, sin esa opción de comprobación. `jarsigner -verify` confirmó su integridad y `keytool -printcert -jarfile` confirmó el certificado original indicado arriba. Tamaño: 59.746.807 bytes; SHA256 `c3faa0c7ccf24f5c1cf9d6c66d5a2861ba1b09c122a528f1dbee93d1a8ceab55`. Se conserva en los informes locales, separado del APK de depuración. No se subió a Play Console ni se publicó.

## Evidencias locales

Los registros, vistas Flutter con datos ficticios y el resultado de compilación se conservan en `C:\Users\LENOVO\Documents\Codex\2026-10-31\ab\outputs`. Véase allí `SEISMIK-APP-V71-PREPARADA.md` para los resultados finales y hashes de artefactos.
