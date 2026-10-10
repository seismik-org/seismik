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

El repositorio es de código visible, no de reutilización libre. Lee [LICENSE](LICENSE)
antes de proponer un aporte. No envíes código de terceros sin sus permisos y avisos.
Los derechos de aportes anteriores bajo Apache-2.0 se conservan. Para nuevos aportes,
acuerda por escrito con los mantenedores los permisos de incorporación, modificación
y distribución antes de aceptarlos; no se presume cesión de propiedad. Respeta el
`CODE_OF_CONDUCT.md`.
