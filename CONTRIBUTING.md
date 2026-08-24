# Contribuir a Seismik

Gracias por mejorar Seismik. Este proyecto acepta issues y pull requests para
backend, móvil, DSP, fuentes sísmicas, accesibilidad, traducciones y documentación.

## Flujo

1. Abre un issue para cambios de comportamiento, seguridad o arquitectura.
2. Crea una rama corta desde `main`.
3. No incluyas credenciales, tokens Firebase/APNs, datos personales ni reportes reales.
4. Añade pruebas y actualiza la documentación afectada.
5. Ejecuta `pytest`, `ruff check src tests`, `mypy src`, `flutter analyze` y
   `flutter test` según corresponda.
6. Envía un pull request explicando riesgos, validación y plan de reversión.

Los cambios que alteren umbrales, coincidencia, alertas críticas, privacidad o
enrutamiento oficial requieren revisión de dos mantenedores y evidencia de replay
o simulación. Los proveedores externos deben tener licencia y términos documentados.

Al contribuir aceptas publicar tu aporte bajo Apache-2.0 y respetar el
`CODE_OF_CONDUCT.md`.
