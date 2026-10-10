# Ajustes para clientes — 10 de octubre de 2026

- Android y SwiftUI iOS: se retiraron etiquetas de build/beta del encabezado y
  diagnóstico, sin alterar la clasificación científica de eventos preliminares
  ni la evaluación de ML. Se conservan los avisos de independencia y seguridad.
- Android: botones de Google, Apple, GitHub y correo mediante el flujo existente
  del navegador con PKCE. El endpoint público de disponibilidad confirmó los
  tres proveedores habilitados; esto no sustituye un login real con cada cuenta.
- Ambas plataformas: acceso al formulario de eliminación de cuenta de Seismik,
  independiente del proveedor con el que se inició sesión. No elimina la cuenta
  de Apple, GitHub o Google; abre la solicitud de eliminación de Seismik.
- Android: términos, privacidad, código fuente/licencia (no «código abierto»).
- iOS: fuentes originales SGC, USGS, IGP, INGV, GeoNet, BMKG, JMA y EMSC,
  con aviso visible de no afiliación gubernamental.
- Material You: Android 14+ lee los roles de color dinámico resueltos del sistema
  (incluidos fondos y contenedores) sin regenerarlos desde una semilla ni una
  tabla fija de tonos. Android 12–13 conservan la compatibilidad de dynamic_color;
  sistemas anteriores usan el tema de respaldo. Se refresca al volver a la app.
  Los colores semánticos de peligro no se sustituyen por colores decorativos.

Referencias técnicas:
https://developer.android.com/reference/android/R.color
https://developer.android.com/develop/ui/views/theming/dynamic-colors

Verificación local: 644 pruebas de Python, 151 de Flutter, Ruff, mypy y análisis
de Dart aprobados. Las pruebas incluyen preservación exacta de colores nativos,
respuesta incompleta de la plataforma y los flujos PKCE de Apple/GitHub.
La compilación de comprobación Android (`flutter build apk --debug --no-pub`)
finalizó correctamente. El APK de depuración no es un release de distribución
ni se instaló sobre la aplicación de Google Play.

Pendiente para distribución: pruebas físicas de paleta clara/oscura y cambio de
fondo en Samsung y Pixel; login/retorno y formulario de eliminación; compilación
SwiftUI en macOS/Xcode. Cambiar textos no certifica el detector ni publica una
versión en las tiendas. No se modifica la firma ni la configuración Firebase.
