# Seismik Mobile

Cliente Flutter 3.47 para Android e iOS. Incluye monitor sísmico, alertas críticas,
DSP voluntario del acelerómetro, reportes oficiales, “¿lo sentiste?” y daños.

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
