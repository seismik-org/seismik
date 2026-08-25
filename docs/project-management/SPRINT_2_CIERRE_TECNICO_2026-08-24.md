# Seismik — cierre técnico Sprint 2

Versión: 1.0  
Fecha de corte: 2026-08-24 (America/Bogota)  
Estado: trabajo de ingeniería terminado; aceptación científica externa pendiente

## Objetivo y resultado

Parametrizar, medir y endurecer el detector en modo sombra sin convertir un
resultado de laboratorio en una promesa de alerta pública. Se completaron S2-01
a S2-05. S2-06 queda pendiente del Product Owner y un asesor independiente.

| ID | Estado | Entregable | Resultado |
|---|---|---|---|
| S2-01 | CO | Perfiles por red | `CM.HHZ`: STA 1 s, LTA 20 s, 1–10 Hz, entrada 6.0, salida 1.2 |
| S2-02 | CO | Coincidencia endurecida | 3 estaciones localizadas, 10 s, apertura ≥50 km y lag ≤15 s |
| S2-03 | CO técnico | Matrices reproducibles | 36 perfiles principales y 18 de contraste con quorum 2 |
| S2-04 | CO técnico | Correlación oficial | Umbral 300 s/600 km, bordes probados y contrato SGC normalizado |
| S2-05 | CO | Salud de estaciones | fresh/stale/high-lag visible; una estación atrasada no aporta quorum |
| S2-06 | BL externo | Acta sismológica | Requiere universidad o profesional independiente |

## Resultado medido

| Configuración | Históricos detectados | Ambiente falso | Duplicados | Latencia media |
|---|---:|---:|---:|---:|
| Adoptada, quorum 3 | 3/3 | 0 | 0 | 56.552 s |
| Mejor contraste, quorum 2 | 3/3 | 0 | 3 | 23.755 s |

El quorum 2 no se adopta: generó tres duplicados y dos detecciones históricas
fuera de la ventana objetivo. El quorum 3 es más estable en este corpus, pero su
latencia es demasiado alta para afirmar utilidad EEW general. El resultado solo
es una calibración de ingeniería sobre tres eventos y cinco minutos de ambiente.

## Reporte oficial SGC

El runtime consulta el feed rápido quincenal del SGC después del candidato. El
payload SGC se normaliza y el matcher acepta como máximo 300 s y 600 km respecto
al tiempo y centroide de las estaciones. La consulta se acotó al margen del
candidato para que un replay antiguo no descargue años de catálogo.

El feed rápido no devolvió los tres replays al momento del cierre: los dos de
2023 y el de 2026 ya estaban fuera de su ventana vigente. Esta limitación queda
registrada en `data/calibration/sgc-association.json`; los metadatos históricos
del manifest proceden del catálogo USGS y las ondas de EarthScope/SGC FDSN.

## Checkpoint

- Configuración sombra reproducible: aprobada para continuar ingeniería.
- Alertas públicas, Critical Alerts e IoT: **No-Go**.
- GCP/facturación: no activados ni necesarios para este Sprint.
- Revisión científica independiente: pendiente y obligatoria.
- Siguiente paso técnico tras la revisión: ampliar ruido continuo y eventos
  pequeños/regionales, medir tasas por día y estudiar una red más densa.

## Evidencia

- `data/calibration/sprint2-grid-expanded.json`
- `data/calibration/sprint2-two-station-tradeoff.json`
- `data/replay/results-sprint2/`
- `data/calibration/sgc-association.json`
- `tests/test_processor.py`, `test_coincidence.py`, `test_seedlink.py`,
  `test_evaluation.py`, `test_official.py`
