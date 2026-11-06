# Miniaturas y visor de LiveAhora publicados

Fecha local: 5 de noviembre de 2026, America/Bogota.

El panel https://liveahora.seismik.org/admin/ permite seleccionar miniaturas JPG,
PNG y WebP estáticas de hasta 5 MB. Se guardan junto con el evento mediante una
transacción; las imágenes de borradores requieren la misma sesión administradora.
El servidor valida el contenido, descarta metadatos y reduce las imágenes a WebP.

«Ver» abre una elección entre la plataforma externa y «Mirar aquí». Esta última
opción aparece para enlaces que identifican un video concreto de YouTube. El
iframe usa exclusivamente `www.youtube-nocookie.com/embed/VIDEO_ID`, se carga
después de la elección y se destruye al cerrar. Canales, Kick y Twitch conservan
la salida a la plataforma. Las políticas explican la conexión con Google al
cargar el reproductor. Las miniaturas no se descargan desde YouTube por adelantado.

## Producción

Proyecto `seismik-15bbb`, región `us-east1`. Ambos servicios reciben 100 % del tráfico.

| Componente | Versión actual | Versión anterior conservada |
| --- | --- | --- |
| API | `seismik-api-liveahora-media-1105` | `seismik-api-family-enabled-1105` |
| Web | `seismik-web-liveahora-media-1105` | `seismik-web-showcase-agencies-1102` |
| Worker | `f7b86fc5`, prefijo mostrado como activo | `4608d337`, prefijo anterior |

Fuentes: commit `153f359a50b1c9de95d275102c581ecfb3cc1e28`, enviado a
`incident/family-continuity-20261102`.

Cloud Build `7780fa7d-2675-40eb-8f89-059829cd880a`: SUCCESS.

- API: `us-east1-docker.pkg.dev/seismik-15bbb/seismik/api@sha256:33141687e1a740e9331057d8b110ab1cc7cc3ee2c43ce7c9feef472723c69e68`.
- Web: `us-east1-docker.pkg.dev/seismik-15bbb/seismik/web@sha256:cd1e19621afd682d14b144b190aea90c07bb6079a5c1e64fcf034c045321558f`.

Las imágenes son capas sobre los digests activos anteriores. La compilación
comparó primero las fuentes originales de LiveAhora con la versión revisada;
no reconstruyó los otros módulos desde una rama potencialmente antigua. Se
verificaron las especificaciones completas de ejecución, admitiendo como único
cambio la imagen: variables, referencias de secretos, identidad, recursos,
sondas, red y volúmenes conservados. Familia sigue habilitada.

Cloudflare preparó una versión mediante su integración Git; se promovió
explícitamente a 100 %. Se contrastó el historial de fuentes preservadas de
LiveAhora y se verificaron las cabeceras reales antes y después: el cambio de
CSP corresponde a LiveAhora. Auth, Developers, Status y Grupo mantuvieron sus
cabeceras y devolvieron 200. La API protegida siguió rechazando acceso directo
sin el secreto de borde. D1 y la autenticación del origen siguieron funcionando.

No se modificaron DNS, IAM, secretos, reglas de Firebase/Firestore ni servicios
sísmicos. Se retiraron sólo las etiquetas nuevas `liveahora-media-review`; las
revisiones y etiquetas anteriores permanecen conservadas.

## Datos y comprobaciones

La comparación final del documento completo del cronograma con su copia previa
devolvió igualdad. No se crearon, editaron ni eliminaron eventos en producción.
La vista previa de archivo seleccionada en el panel se restableció sin guardar.

Respaldo privado y evidencia de configuración en Cloud Shell:
`~/liveahora-media-20261105/`, con `schedule-before.json`, `schedule-after.json`,
configuraciones previas/finales, comprobaciones y `release-summary.json`.
SHA-256 de la copia previa:
`8f7536926e4de419ff0feb064b7ad98d20edeeb2a3bad001b5c69678ea0c4b4d`.

- 22 pruebas Python de LiveAhora aprobadas, incluidas miniaturas privadas,
  conversión, conflictos, entradas inválidas, límite del cuerpo y eliminación.
- 156 pruebas Python de web, seguridad de borde y despliegue aprobadas.
- 22 pruebas Node de presentación, selección de video, enrutamiento y respaldo.
- Ruff, comprobación de sintaxis JavaScript y revisión del diff aprobados.
- Revisiones aisladas: salud, Firestore real, protección del borde, administración
  sin sesión rechazada y recursos nuevos comprobados antes de recibir tráfico.
- Chrome real: sesión central de `liveahora@seismik.org`, selección y vista previa
  de miniatura, diálogo público y reproductor del video publicado
  `u4asBmizyV8`; cero iframes antes de elegir y después de cerrar.

La persistencia de una miniatura y su ciclo completo se comprobaron con dobles
controlados de Firestore. No se hizo una escritura de prueba en producción sobre
el contenido del usuario. La lectura real y los permisos existentes de la misma
base se conservaron; no se concedieron permisos adicionales para imágenes.

## Reversión

Consultar primero la configuración actual y los cambios posteriores. Conservar
la base y `liveahora_media` al revertir código. Tras subir una miniatura, no
restaurar una API cuyo validador sólo admita las dos imágenes locales: necesita
seguir entendiendo las rutas de imágenes nuevas. Evitar editar con una interfaz
antigua que no conserve la opción de miniatura subida. No restaurar un cronograma
antiguo sobre publicaciones posteriores del usuario.
