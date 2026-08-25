# Casos de replay MiniSEED

Este directorio contiene tres ventanas de sismos historicos colombianos y una
ventana de ruido ambiente. `manifest.json` registra origen, ventana temporal,
estaciones disponibles, tamano y SHA-256 de cada fixture.

Los datos de onda de la red `CM` son operados por el Servicio Geologico
Colombiano y se descargan mediante EarthScope FDSN. Los metadatos de evento se
referencian a USGS. Estos datos de terceros conservan sus condiciones y
atribucion de origen; la licencia Apache-2.0 del codigo no pretende relicenciarlos.

Regenerar evidencia:

```powershell
.\.venv\Scripts\python.exe tools\prepare_replay_cases.py
```

Ejecutar un caso sin esperas de reloj real:

```powershell
.\.venv\Scripts\python.exe -m eew.replay `
  --config config.json `
  --manifest data\replay\manifest.json `
  --case co-2023-08-17-m6.1 `
  --output work\replay-co-2023-08-17.json
```

Los fixtures sirven para ingenieria reproducible; no constituyen por si solos
una validacion sismologica ni autorizan alertas publicas.

## Resultado Sprint 2

La red de prueba se amplio a 15 estaciones configuradas; cada fixture contiene
11 o 12 estaciones segun disponibilidad del archivo. La configuracion sombra
adoptada (`STA=1 s`, `LTA=20 s`, umbral de entrada `6.0`, quorum de 3 estaciones
en 10 s y apertura minima de 50 km) produjo un candidato por evento historico y
cero candidatos en la ventana ambiente:

| Caso | Candidatos | Latencia desde origen |
|---|---:|---:|
| co-2026-08-10-m7.4 | 1 | 52.793 s |
| co-2023-08-17-m6.1 | 1 | 56.208 s |
| co-2023-08-27-m5.7 | 1 | 60.655 s |
| co-2026-08-24-ambient | 0 | No aplica |

La media de 56.552 s no permite afirmar que exista alerta temprana util cerca
del epicentro. Cinco minutos de ruido tampoco estiman una tasa de falsa alarma
operacional. `results-sprint2/` conserva la salida y `data/calibration/` conserva
la matriz y el experimento de dos estaciones, que fue descartado por duplicados
y asociaciones fuera de la ventana de evaluacion.
