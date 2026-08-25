# Seismik — paquete de revisión sismológica

Versión: 0.1  
Estado: listo para revisión independiente; no aprobado científicamente  
Responsable de conseguir revisor: Product Owner

## Propósito

Solicitar una revisión independiente del detector sombra colombiano. No se pide
certificar un sistema público: se pide identificar errores metodológicos, sesgos
del corpus y el experimento mínimo siguiente.

## Material a revisar

1. `config.json`, secciones `detection` y `coincidence`.
2. `src/eew/processor.py` y `src/eew/coincidence.py`.
3. `data/replay/manifest.json` y `data/replay/README.md`.
4. `data/calibration/sprint2-grid-expanded.json`.
5. `data/calibration/sprint2-two-station-tradeoff.json`.
6. `SPRINT_2_CIERRE_TECNICO_2026-08-24.md`.

## Preguntas para el revisor

- ¿Son apropiados 1–10 Hz, STA 1 s y LTA 20 s para HHZ de la red CM?
- ¿El umbral 6.0/1.2 y la ventana multiestación de 10 s introducen sesgo hacia
  eventos grandes o lejanos?
- ¿La apertura de 50 km ayuda a rechazar ruido local sin impedir eventos reales?
- ¿Qué eventos, duraciones de ruido y estaciones faltan para estimar sensibilidad
  y falsa alarma con intervalos de confianza?
- ¿Debe calcularse tiempo de origen/hipocentro antes de evaluar utilidad EEW?
- ¿Qué criterio objetivo debe bloquear o permitir un piloto cerrado?

## Formato de respuesta solicitado

| Campo | Respuesta del revisor |
|---|---|
| Nombre, entidad y experiencia | Pendiente |
| Fecha y versión revisada | Pendiente |
| Hallazgos críticos | Pendiente |
| Cambios obligatorios | Pendiente |
| Experimentos adicionales | Pendiente |
| Apto para modo sombra prolongado | Sí / No / Condicionado |
| Apto para alertas a personas | No es objeto de esta revisión inicial |

## Advertencia

Tres sismos detectados y cinco minutos sin falsos candidatos no demuestran
sensibilidad, especificidad ni disponibilidad operacional. Hasta completar esta
revisión y un shadow run prolongado, Seismik permanece en No-Go público.
