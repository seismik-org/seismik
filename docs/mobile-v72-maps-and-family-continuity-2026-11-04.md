# Android v72: Maps y continuidad de Familia

## Corrección de Maps

El AAB de v71 contenía la entrada `com.google.android.geo.API_KEY` vacía. La compilación directa con Flutter podía omitir el control del script de firma.

Gradle ahora rechaza una compilación release distribuible sin `SEISMIK_GOOGLE_MAPS_API_KEY`. La excepción de CI existente permite exclusivamente una comprobación sin keystore de producción; ese artefacto no debe distribuirse.

`tools/build-signed-release.ps1` carga la clave desde una copia DPAPI fuera del repositorio cuando no se ha definido en el entorno. `tools/verify_android_maps_bundle.py` comprueba el manifest protobuf del AAB real, el paquete `com.seismik.app` y la coincidencia exacta de la clave. No imprime su valor.

La clave existente proporcionada por el usuario coincide con «Seismik Android Maps» en GCP. Se mantuvieron sus restricciones: Maps SDK for Android y aplicaciones Android. La huella SHA-1 del certificado de distribución descargado de Play Console (`20:52:37:2B:C3:7E:40:A5:95:5B:6D:A5:DB:42:99:A0:91:BB:9A:59`) ya estaba autorizada. No se sustituyó ninguna clave ni certificado.

## Artefacto verificado

- Versión: `1.0.0+72`.
- AAB SHA-256: `DCDA0ED90F755C05807637DD7610C0B803D39F89BA0272DE64C3C93BC4B462EC`.
- Certificado de subida SHA-256: `83:27:89:71:F1:D8:7C:3E:FC:CC:DD:17:98:D2:C6:5C:6D:F8:C1:20:BB:8E:2B:16:EA:42:17:E3:9E:F6:BE:E0`.
- `jarsigner -verify`: firma verificada; certificado de subida autofirmado, como el original.
- Verificador del AAB: PASS con la clave esperada. AAB anterior v71: rechazado por clave vacía.
- Prueba negativa de Gradle sin clave: rechazo en `preReleaseBuild`.
- 200 pruebas Flutter y análisis sin incidencias; 798 pruebas Python del trabajo de continuidad aprobadas. Ruff del verificador y sintaxis PowerShell aprobados.

No había ningún dispositivo ADB conectado. La configuración y el artefacto están comprobados; la carga visual de los mapas en un teléfono aún requiere validación real después de actualizar desde el canal interno, conservando los datos de la app.

## Publicación

Google Play confirmó el 4 de noviembre de 2026 a las 12:01 de Colombia la versión «72 - Maps y continuidad familiar» como **Disponible para verificadores internos**, en el canal interno existente. Release 13, track `4701297958425543883`. Producción continúa inactiva. No se reemplazó ni eliminó la versión histórica 71.

## Protección de Familia

El cliente distingue la ausencia explícita de un círculo de un 404 genérico. Conserva la última lista local cuando el servidor no encuentra el círculo y evita ofrecer crear/unirse ante un error de consulta. El servidor incluye un modo de recuperación que impide cambios en Familia y devuelve 503 autenticado.

Estas medidas NO recuperan los círculos históricos. El examen previo de Redis no encontró círculos ni una copia histórica utilizable. La copia nueva creada durante el incidente conserva únicamente el estado actual. La activación final del modo de recuperación en producción y la operación de persistencia RDB requieren contrastar el resultado actual de GCP; no deben darse por confirmadas por la mera existencia del código o de una revisión preparada.

## Manejo local de la clave

La copia DPAPI pertenece al usuario y equipo Windows actuales. El archivo de entrada en Bloc de notas sigue pendiente de retirada manual por el usuario; no se incluyó en Git, informes ni artefactos de transferencia. No copiar secretos a documentación ni a comandos de publicación.
