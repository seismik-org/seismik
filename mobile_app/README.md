# Seismik Mobile

Cliente Flutter 3.47 para Android e iOS. Incluye monitor sísmico, alertas críticas,
DSP voluntario del acelerómetro, reportes oficiales, “¿lo sentiste?” y daños.

La versión 0.6.2 incorpora el logotipo, Google Maps y un menú Material 3 con
Historial de Sismos, Sismo sentido, Reporte de daños y Configuración. El menú
reserva espacio real, respeta las barras del sistema y se oculta cuando aparece
el teclado para no bloquear formularios.

En Configuración → Alertas críticas se puede abrir el permiso especial de
pantalla completa requerido por Android 14+ y ejecutar una simulación local.
La simulación no crea un evento en el backend ni notifica a otros teléfonos. La
app también recupera el payload si Android tuvo que iniciar un proceso terminado
desde una alerta crítica. Con el teléfono desbloqueado, Android puede conservar
la otra app visible y presentar un aviso emergente; la intención abre la pantalla
completa cuando el equipo está bloqueado o con la pantalla apagada.

La interfaz aparece antes de completar ubicación, Firebase, App Check y el
registro push. En una beta instalada fuera de Play Store se permite un marcador
de integridad no verificado solamente mientras el backend conserve
`SEISMIK_INTEGRITY_VERIFICATION_ENABLED=false`; producción debe compilar con
`SEISMIK_INTEGRITY_REQUIRED=true` y verificar Play Integrity.

En Android 12 o posterior `dynamic_color` lee el `CorePalette` completo publicado
por Android/One UI: primarios, secundarios, terciarios, superficies y sus tonos
claro/oscuro. No se reconstruye la interfaz a partir de un solo color. La pantalla
de Configuración permite activar/desactivar esa paleta, elegir modo del sistema,
claro u oscuro y aplicar el cambio inmediatamente.

El historial consulta el agregador de Seismik para SGC, USGS, IGP, INGV,
GeoNet, BMKG y JMA, conserva una copia offline y permite elegir fuentes, periodo
y magnitud mínima. Cada ficha mantiene atribución y enlace a la fuente oficial.

En cada sismo, “¿Lo sentiste?” permite escoger las organizaciones geológicas
disponibles para el país. La selección se guarda localmente por evento. Si no hay
Internet se muestra el catálogo integrado; el reporte a Seismik y la apertura del
formulario oficial son acciones independientes y ninguna entidad recibe datos
automáticamente.

## Desarrollo

```bash
flutter pub get
flutter analyze
flutter test
flutter run --dart-define=SEISMIK_API_BASE_URL=https://api.example.org \
  --dart-define=SEISMIK_DEVICE_KEY=bootstrap-de-desarrollo
```

La URL predeterminada es `https://api.seismik.org`; la clave de dispositivo
continúa siendo obligatoria en compilaciones release.

Google Maps requiere una clave restringida a Maps SDK for Android y al paquete
`com.seismik.app`. No se versiona la clave. En PowerShell:

```powershell
$env:SEISMIK_GOOGLE_MAPS_API_KEY = 'clave-restringida'
flutter build apk --debug --split-per-abi
```

Sin esa variable el proyecto compila, pero el mapa no carga mosaicos en el
dispositivo. La clave de iOS se suministra como build setting
`SEISMIK_GOOGLE_MAPS_API_KEY` en Xcode.

Añade fuera de Git `android/app/google-services.json` y
`ios/Runner/GoogleService-Info.plist`. Las alertas críticas iOS requieren el
entitlement aprobado por Apple; Android requiere permiso del usuario para
notificaciones y full-screen intent. Consulta el README raíz para producción.
