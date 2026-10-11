# Permisos críticos de entrada y simulacros en iPhone (build 63)

## Por qué los simulacros no llegaban al iPhone

Había **dos** causas, una de servidor y una de la app:

1. **APNs rechazaba el aviso** (`403 InvalidProviderToken` en los registros del dispatcher: `aioapns ... is 403`).
   El dispatcher tenía `SEISMIK_APNS_KEY_ID=QGN8M6TWM6`, que es la clave de *Sign in with Apple*
   y no sirve para APNs. La clave de APNs/DeviceCheck del equipo `ZW23DHZDGB` es `8CUMWT56JZ`.
   Se corrigió en el servicio `seismik-dispatcher` (revisión `00053`). Los avisos a Android seguían
   saliendo (`attempted=3 succeeded=2`), por eso sólo fallaba iOS.
2. **iOS nunca pedía el permiso de notificaciones en el primer arranque.** Se pedía sólo al pulsar
   «Activar alertas» en Configuración; sin él, el aviso llega al teléfono pero iOS no lo muestra, y el
   dispatcher lo trataba como un teléfono sin alertas críticas (`critical_alerts_authorized=false`).

## Qué cambia en la app (build 63)

- **iPhone:** la primera pantalla es una bienvenida (`PermissionsOnboardingView`) que pide de entrada
  notificaciones con alertas críticas y la ubicación mientras se usa la app. «Ahora no» la cierra y vuelve a
  aparecer en la siguiente apertura mientras la persona no haya decidido; si ya negó algo, no se le insiste.
  Configuración > Alertas críticas sigue permitiendo cambiarlo.
- **iPhone:** un simulacro (`drill-…`) suena como alarma pero ya no se guarda en el historial.
- **Android:** al abrir por primera vez, después de los diálogos de notificaciones y ubicación, se lleva
  a la persona a la página «Permitir alertas a pantalla completa» (Android 14+), una sola vez. Antes estaba
  sólo en Configuración. La pantalla se marca como mostrada antes de abrirse (`FirstRunPermissions`).

## Qué no cambia

- No se añade la capacidad *Time Sensitive Notifications*: exige regenerar el perfil de distribución y, si el
  perfil no la trae, rompe la firma. Sin ella, un simulacro crítico en un iPhone que **no** concedió alertas
  críticas llega como aviso normal. Con el permiso concedido llega como alerta crítica con sonido.
- Android no pide todavía «No molestar» ni la exención de batería: necesitan código nativo.

## Cómo comprobarlo

1. Instalar la build 63 en un iPhone **nuevo o con la app borrada** (los permisos ya negados no se vuelven a pedir).
2. Abrir: aparece la bienvenida; «Activar ahora» muestra notificaciones, alertas críticas y ubicación.
3. En el panel admin > Pruebas, inscribir el teléfono y enviar un simulacro crítico: debe sonar con el
   teléfono en silencio. Un `403 InvalidProviderToken` en los registros del dispatcher significa que la clave
   APNs y su identificador no coinciden (revisar `SEISMIK_APNS_KEY_ID` y el secreto `seismik-apns-private-key`).
