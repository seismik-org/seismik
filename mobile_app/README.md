# Seismik Mobile

Cliente Flutter 3.47 para Android e iOS. Incluye monitor sísmico, alertas críticas,
DSP voluntario del acelerómetro, reportes oficiales, “¿lo sentiste?” y daños.

La versión 0.5.1 incorpora el logotipo oficial, Google Maps y un menú Material 3
flotante con Historial de Sismos, Sismo sentido, Reporte de daños y Configuración.
En Android 12 o posterior lee directamente `system_accent1_500`, el código ARGB
que Android/One UI publica para la paleta Material You seleccionada por el
usuario. Ese valor se conserva como color primario exacto en modo claro y oscuro;
solo se usa la semilla Seismik de respaldo si el sistema no publica el recurso.

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
