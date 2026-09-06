# Cierre técnico — Sprint 5: reportes comunitarios

## Entrega

- Reporte «Sismo sentido» firmado, idempotente y con selección explícita de
  formularios oficiales.
- Reporte textual de daños y peligros, con advertencia de emergencia para
  heridos, atrapados, fuego, gas o colapso.
- Privacidad por defecto: ubicación aproximada; precisión exacta sólo con
  consentimiento de la persona.
- Cola persistente offline, reintentos ordenados, expiración, descarte de
  rechazos permanentes y sincronización al volver la app a primer plano.
- Formularios oficiales abiertos mediante Chrome Custom Tabs / Safari
  integrado, no en un navegador externo.

## Verificación técnica

- Backend: `pytest -q` correcto.
- Flutter: `flutter test` correcto (46 pruebas).
- `flutter analyze` correcto en los cambios de la app.

## Límite decidido

No hay fotos ni vídeo en esta entrega. DEC-003 los aplaza hasta contar con
almacenamiento seguro, límites de tamaño, retención, moderación, borrado y
presupuesto aprobados. No se almacenan adjuntos en Redis ni en la cola local.

## Aceptación completada

El Product Owner confirmó en Android físico: modo avión, guardado de reporte,
reinicio de Seismik, recuperación de Internet y sincronización única.
