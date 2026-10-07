# Boletines automáticos en Facebook

Facebook publica los mismos catálogos oficiales e imágenes del publicador de X,
con sus umbrales, ventana de antigüedad, exclusiones y preferencia por agencias
locales (`SEISMIK_X_PUBLISHER_*`). No publica simulacros ni reportes retirados.
La automatización es por eventos, no por horario de publicaciones comerciales.

Corre en el proceso existente de integraciones, sin un nuevo servicio Cloud Run.
X conserva sus credenciales y sus marcas. Facebook tiene marcas y auditoría
independientes: `seismik:facebook:*` y `stream:seismik:facebook-audit`.

## Activación

1. Configurar una aplicación de Meta con acceso a la página Seismik
   (ID Graph `1426821820505734`, confirmado con `me?fields=id,name`). El ID
   del perfil público puede ser distinto; usar siempre el devuelto por Graph.
   Obtener un token de página con los permisos que Meta
   requiere para publicar: `pages_manage_posts`, `pages_read_engagement`.
   La obtención/listado de páginas puede requerir `pages_show_list`.
2. Guardarlo en Secret Manager como `seismik-facebook-page-access-token` y
   conceder acceso al servicio existente. Nunca pegarlo en Git, logs o chats.
3. En `seismik-dispatcher`, montar el secreto como
   `SEISMIK_FACEBOOK_PAGE_ACCESS_TOKEN`, definir `SEISMIK_FACEBOOK_PAGE_ID`,
   `SEISMIK_FACEBOOK_GRAPH_VERSION` (por defecto `v26.0`), y activar
   `SEISMIK_FACEBOOK_PUBLISHER_ENABLED=true` con
   `SEISMIK_FACEBOOK_PUBLISHER_DRY_RUN=true` inicialmente.
4. Revisar la auditoría y el boletín; cambiar dry-run a false. Los eventos de
   prueba ya marcados no se vuelven a publicar. Verificar un boletín nuevo en
   la página y vigilar revocación/caducidad del token.

La configuración permanece apagada por defecto. Los despliegues conservan las
variables y referencias a secretos existentes de Cloud Run.

Un rechazo HTTP libera la marca para un reintento finito. Si se pierde la
respuesta, Meta devuelve un error de servidor o no hay ID, se registra
`delivery_uncertain` y se conserva la marca para evitar duplicados por reintento
ciego. Revisar esos casos manualmente antes de volver a enviar. No hay garantía
de entrega exactamente una vez entre Redis y la API de Meta.

Referencias: https://developers.facebook.com/docs/pages-api/posts/ y
https://developers.facebook.com/docs/graph-api/reference/page/photos/.
