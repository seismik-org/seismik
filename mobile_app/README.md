# Seismik Mobile

Cliente Flutter 3.47 para Android e iOS. Incluye monitor sísmico, alertas críticas,
DSP voluntario del acelerómetro, reportes oficiales, “¿lo sentiste?” y daños.

La interfaz usa Material 3/Material You: en Android 12 o superior toma la paleta
del fondo configurado por el usuario y en otros sistemas usa una paleta Seismik
de respaldo. Respeta automáticamente el modo claro u oscuro del sistema.

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

Añade fuera de Git `android/app/google-services.json` y
`ios/Runner/GoogleService-Info.plist`. Las alertas críticas iOS requieren el
entitlement aprobado por Apple; Android requiere permiso del usuario para
notificaciones y full-screen intent. Consulta el README raíz para producción.
