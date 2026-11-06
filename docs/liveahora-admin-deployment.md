# LiveAhora: web, cronograma y /admin

La web pública se sirve desde el origen web existente y el Worker dirige
`liveahora.seismik.org/admin/` a `web/liveahora/admin/`. Las peticiones
`/v1/liveahora/` van al origen API con el secreto de origen ya existente.
No se necesita un subdominio profundo ni ACM.

## Identidad y almacenamiento

- El panel inicia sesión en `auth.seismik.org`; el retorno es una URL fija de
  LiveAhora, no una dirección recibida del navegador.
- El backend reutiliza la sesión central, incluida la validación de revocación
  Firebase cuando corresponda. Sólo `liveahora@seismik.org` está autorizado.
- `SEISMIK_LIVEAHORA_ADMIN_UID` permite fijar además el identificador de la
  identidad. Antes de publicar, resolverlo desde la cuenta central y fijarlo.
- Los eventos se guardan en Firestore Native, base nombrada `liveahora`, documento
  `liveahora_calendar/schedule`. No usa la base `(default)` de otras aplicaciones.
- El cliente servidor usa ADC de la cuenta de ejecución de Cloud Run. No hay
  claves privadas exportadas en la web o en el repositorio.
- Crear la base con acceso directo de clientes denegado y revisar sus reglas.
  La lectura pública y todas las escrituras pasan por la API. No añadir reglas
  públicas de Firestore para el calendario.
- Verificar los permisos IAM de la identidad del servicio para esta base antes
  de desplegar. Si requieren ampliación, revisar el permiso concreto con el
  propietario; no conceder roles globales de Owner o Editor para resolverlo.

## Preparación y publicación

1. Revisar la configuración existente de los servicios `seismik-api` y
   `seismik-web`, su cuenta de ejecución y el enrutador. Conservar secretos,
   variables, revisiones anteriores y configuración de sesión.
2. Verificar o crear Firestore Native `liveahora`, elegir su región con el
   propietario y revisar coste y permisos. No crear un nuevo proyecto Firebase.
3. Confirmar que la cuenta central `liveahora@seismik.org` existe, está verificada
   y puede iniciar sesión. Fijar el UID autorizado en configuración de la API.
4. Construir y desplegar la API con la nueva ruta y el retorno OAuth, manteniendo
   los secretos y permisos existentes. Construir y desplegar el origen web.
5. Publicar el Worker actualizado desde la fuente verificada. Las dos copias del
   enrutador deben permanecer iguales.
6. Verificar DNS y cobertura de la ruta del Worker para `liveahora.seismik.org`,
   certificado activo y cabeceras. No modificar los demás dominios.
7. Probar inicio y cierre de sesión real, cuenta no autorizada, borrador, evento
   publicado, edición y cancelación. Comprobar privacidad y horario de Colombia.
   Retirar únicamente el evento de prueba creado durante esta validación.

## Comportamiento

Máximo 100 eventos. Los cambios usan transacciones y una revisión para evitar
sobrescrituras. Hay un límite de 30 escrituras por minuto y cuenta. Las entradas
se validan en el servidor y las mutaciones requieren el origen de LiveAhora y
una cabecera propia. Los títulos y descripciones se muestran como texto.

Sólo se aceptan enlaces HTTPS de YouTube, Kick o Twitch. La administración puede
elegir dos imágenes locales o subir una miniatura JPG, PNG o WebP estática de hasta
5 MB, 8192 píxeles por lado y 16 megapíxeles. El servidor descarta metadatos,
reduce a 1280 × 720 como máximo y convierte a WebP de hasta 180 KB. La imagen y el
evento se guardan en una misma transacción. Las imágenes quedan en documentos
separados `liveahora_media/{event_id}` de la misma base, con como máximo dos
versiones por evento; no engordan el documento del cronograma. Eliminar un evento
también elimina su documento de imágenes. La API sólo sirve públicamente la
miniatura actual de un evento público; los borradores requieren sesión administradora.
No se añaden claves, permisos IAM ni acceso directo público a Firestore.
El administrador confirma
los derechos antes de publicar. Los borradores y eventos finalizados no se
muestran; los cancelados se muestran hasta el fin previsto si tienen derechos
confirmados. Los eventos salen del cronograma público después de su hora de fin.

La web consulta el cronograma al abrirse y cada 60 segundos mientras está visible.
«En directo» es un estado manual, no una verificación automática de la plataforma.
Cerrar sesión en este panel cierra la sesión central de Seismik del navegador.

«Ver» abre un diálogo para elegir la plataforma externa. Sólo los enlaces a un
video concreto de YouTube ofrecen «Mirar aquí»: carga un iframe de
`https://www.youtube-nocookie.com/embed/VIDEO_ID`, después de esa elección.
Los canales no se convierten en videos supuestos. Cerrar el diálogo destruye el
iframe. Se conserva la alternativa externa para restricciones de inserción.
La CSP de LiveAhora debe permitir `frame-src https://www.youtube-nocookie.com`
y `img-src 'self' blob:` para la vista previa local, sin ampliar otros portales.

Al revertir, conservar una API compatible con las rutas de miniaturas: las
versiones antiguas del validador sólo admitían las dos imágenes locales. No
restaurar un cronograma anterior sobre cambios del usuario ni borrar imágenes
para revertir la interfaz. Los respaldos previos son evidencia, no una orden de
sobrescribir datos actuales.

## Validación pendiente de infraestructura

### Precauciones comprobadas al publicar desde este PC

- La imagen activa de API contiene retornos OAuth adicionales para cuenta,
  vinculación y eliminación, además de campos de correo saliente. No sustituir
  `config.py` u `oauth.py` completos desde esta rama: aplicar únicamente los
  puntos de inserción de LiveAhora sobre el digest verificado y conservar esas
  funciones existentes.
- Un contexto extraído en Cloud Shell con `umask 077` puede dejar los archivos
  nuevos con modo `0600`. El archivo `liveahora.py` debe quedar en `0644` dentro
  de la imagen. Ejecutar la comprobación de importación de la API en la etapa
  final, bajo el usuario heredado de la imagen de producción, no como root.
- El constructor Docker existente no admite `COPY --chmod` sin BuildKit. Usar
  un `RUN chmod 0644 /app/src/api/liveahora.py` en la etapa de preparación y
  conservar el usuario original en la etapa final.
- La identidad de ejecución necesita `roles/datastore.user` condicionado a
  `resource.name == "projects/seismik-15bbb/databases/liveahora"`. La concesión
  debe revisarse expresamente; no reemplaza las reglas restrictivas de clientes.

Las pruebas locales sustituyen Firestore y la sesión con dobles controlados:
no demuestran permisos IAM, reglas desplegadas ni acceso a la cuenta real.
La publicación y las pruebas visuales requieren acceso autorizado del navegador.
