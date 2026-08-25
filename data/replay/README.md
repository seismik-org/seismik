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
