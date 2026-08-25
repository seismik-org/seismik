# Seismik — cierre técnico Sprint 1

Versión: 1.0
Fecha de corte: 2026-08-24 (America/Bogota)
Estado: cerrado técnicamente; revisión sismológica externa pendiente para Sprint 2

## Objetivo

Hacer que la adquisición y la reproducción de formas de onda sean deterministas,
medibles y recuperables sin presentar el prototipo como una alerta pública.

## Resultado por actividad

| ID | Estado | Evidencia | Resultado |
|---|---|---|---|
| S1-01 | Hecho | `.python-version`, `pyproject.toml` | Python 3.12.10; pytest, Ruff y mypy ejecutables |
| S1-02 | Hecho | `data/stations/colombia-stations-2026-08-24.json` | Seis canales CM HHZ activos y con datos recientes |
| S1-03 | Hecho | `src/eew/seedlink.py`, `processor.py`, tests | Backoff con jitter, timeout, corte simulado, gaps/NaN/overlap auditables |
| S1-04 | Hecho | `src/eew/replay.py`, `tests/test_replay.py` | Replay MiniSEED determinista con reloj de la onda |
| S1-05 | Hecho técnico | `data/replay/manifest.json` | Tres sismos y una ventana ambiente, seis estaciones, hashes y atribución |
| S1-06 | Hecho | salida de CI local | 32 pruebas; Ruff y mypy sin hallazgos |

## Medición puntual en vivo

- EarthScope SeedLink: `rtserve.earthscope.org:18000`.
- Stream recibido: `CM.ARGC.00.HHZ`.
- Muestras: 464 a 100 Hz.
- Fin del paquete: `2026-08-25T01:58:10.848Z`.
- Recepción: `2026-08-25T01:58:14.843Z`.
- Lag puntual observado: 3.995 s.

Es una observación de un paquete, no una garantía de continuidad ni SLA. Los
puertos 18000, 18500 y 443 también respondieron al probe TCP de la fecha.

## Replay y hallazgo de seguridad

| Caso | Tipo | Triggers | Candidatos |
|---|---|---:|---:|
| co-2026-08-10-m7.4 | histórico | 67 | 6 |
| co-2023-08-17-m6.1 | histórico | 59 | 6 |
| co-2023-08-27-m5.7 | histórico | 61 | 6 |
| co-2026-08-24-ambient | ambiente | 20 | 2 |

El caso ambiente produjo dos candidatos con la configuración inicial. Esto es
un **No-Go para alertas públicas**, no un fallo oculto. El Sprint 2 debe calibrar
filtro/STA-LTA, medir falsos positivos, incorporar salud/lag por estación y
obtener revisión sismológica antes de cualquier piloto que alerte usuarios.

## Checkpoint

- Ingesta reproducible y recuperable: aprobado para ingeniería.
- Evidencia histórica reproducible: aprobada.
- Calibración científica: pendiente.
- Alertas públicas, Critical Alerts e IoT: bloqueadas por diseño.
- GCP/facturación: no activados ni requeridos para este cierre.
- Docker Compose: validación local pendiente porque Docker no está instalado en
  esta estación; la suite Python y Flutter no depende de esa omisión.

## Validación final

- Backend: 32 pruebas aprobadas.
- Ruff: sin hallazgos en `src`, `tests` y `tools`.
- mypy: sin hallazgos en 33 archivos fuente.
- Flutter: análisis sin problemas y 2 pruebas aprobadas.
- Replay ambiente repetido: JSON idéntico por SHA-256.
- Escaneo local de patrones de secretos: sin coincidencias.

## Comandos de verificación

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src tests tools
.\.venv\Scripts\python.exe -m mypy src
```
