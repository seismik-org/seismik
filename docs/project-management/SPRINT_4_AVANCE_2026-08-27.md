# Seismik — avance técnico Sprint 4

Versión: 0.1  
Fecha de corte: 2026-08-27 (America/Bogota)  
Estado: en curso; **No-Go para alertas públicas**

## Resultado de esta iteración

- Material 3/Material You con color dinámico en Android y paleta de respaldo.
- Modo claro u oscuro controlado por la preferencia del sistema.
- Componentes principales migrados de colores fijos al `ColorScheme` activo.
- Catálogo `GET /v1/reports/agencies` para consultar entidades antes de reportar.
- Selección de una o varias organizaciones por sismo.
- Preferencia guardada localmente e independiente para cada evento.
- Respaldo offline inicial con SGC para Colombia y USGS internacional.
- El servidor valida IDs permitidos y devuelve solo los formularios elegidos.

## Privacidad y alcance

Seleccionar una entidad no autoriza una transmisión automática. El reporte se
guarda primero en Seismik y la pantalla de resultado abre el formulario externo
elegido para que la persona lo revise y lo envíe. Esto evita afirmar una
integración institucional que todavía no existe.

## Validación

- Flutter analyze: sin hallazgos.
- Flutter test: 5 pruebas aprobadas.
- Backend: 57 pruebas aprobadas.
- Ruff: sin hallazgos.
- mypy: sin hallazgos en 34 archivos fuente.
- APK Android debug generado correctamente (160,8 MiB; no es el artefacto
  optimizado de distribución).
- SHA-256 del APK local:
  `703fdfe707b8145bfe685d90f6f7dd21bad99b7194129b59d61683c37834987e`.

La compilación advierte que una versión futura de Flutter exigirá actualizar
Android Gradle Plugin y Kotlin. No bloquea el APK actual y queda registrada como
deuda técnica antes del build de distribución.

## Pendiente para cerrar Sprint 4

1. Cola durable completa para reportes creados sin Internet.
2. Sincronización automática e idempotente al recuperar red.
3. Indicadores visibles de pendiente, enviado y fallido.
4. URL de API beta real, sin dominio `.example`.
5. Pruebas de permisos, reinicio y red intermitente en dos teléfonos Android.
