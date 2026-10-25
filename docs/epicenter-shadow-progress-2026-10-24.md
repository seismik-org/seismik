# Primera etapa del localizador mejorado

## Estado

Motor experimental y replay offline implementados. No conectado todavía al trabajador vivo ni a la API, y no desplegado. No modifica avisos personales, alertas críticas, estaciones o autorización de magnitud beta. No hay infraestructura nueva contratada. Ningún resultado de este módulo autoriza alertas públicas.

## Mejoras construidas

`src/eew/epicenter_shadow.py` incorpora ajuste conjunto de hipótesis P/S con errores de llegada explícitos, semillas distribuidas en una malla regional y refinamiento robusto. Exige cinco estaciones independientes por defecto, rechaza fases duplicadas, S anterior a P, coordenadas incoherentes, observaciones inválidas y entradas que excedan el límite de CPU/memoria. No elimina una estación ruidosa silenciosamente para hacer pasar un resultado.

Compara mínimos alternativos, geometría de estaciones y estabilidad al retirar por turnos una estación completa. Con sólo cinco estaciones declara insuficiente redundancia para esa última comprobación. Incluye una comparación conservadora con un frente plano para señalar posibles ondas lejanas; no es un clasificador de teleseísmos calibrado.

La clase `ProgressiveLocationReview` conserva observaciones por evento, con expiración de 240 s, máximo 16 eventos, límite de estaciones y frecuencia de revisión. Puede incorporar una llegada posterior sin esperar el temporizador de 270 s de la ML. **Esta capacidad está probada con pruebas unitarias, pero aún no conectada al detector en vivo.** Debe invocarse desde su trabajador de fondo, nunca desde el lector SeedLink.

Todas las salidas tienen `validation_status=experimental_unvalidated` y `public_alert_eligible=false`. La dispersión entre mínimos y el desplazamiento al retirar estaciones son diagnósticos, no intervalos de confianza calibrados. Los valores de profundidad calculados sólo con hipótesis P se marcan ambiguos. El soporte P/S del motor no significa que ya se haya construido un clasificador automático S.

## Replay de ondas reales

Herramienta: `tools/review_epicenter_shadow.py`. Se solicitaron 108 ventanas verticales: nueve estaciones para los doce avisos de la auditoría del 24 de octubre. EarthScope devolvió 2.506.240 bytes; en estas ventanas no hubo trazas continuas utilizables de CRJC y TUM. Esto describe el archivo recuperado, no demuestra una caída permanente de esas estaciones.

El picker existente de producción extrajo hipótesis P de las ondas, sin utilizar coordenadas ni magnitudes de catálogo como entrada del localizador. Los informes SGC sólo se contrastaron después. El replay permite datos hasta 110 s después del primer disparo: sus tiempos de CPU no son latencia de detección temprana ni equivalen a observación causal en vivo.

| Aviso (Bogotá) | Hipótesis disponibles | Resultado | Error horizontal frente al evento SGC compatible |
| --- | --- | --- | --- |
| 18 oct., 10:24 — El Carmen | Cinco estaciones | Ambiguo: cobertura azimutal de 257°, sin redundancia al retirar estación, sólo P | 54,03 km |
| 20 oct., 17:00 — Los Santos | Cinco estaciones | Ambiguo: RMS 6,65 s, profundidad en borde y otros motivos | 133,50 km |
| 22 oct., 21:13 — Los Santos | Seis estaciones | Ambiguo: sólo P; profundidad no establecida | 25,75 km |
| Los otros nueve avisos | Entre cero y tres estaciones | Datos insuficientes | No se calcula ubicación |

En el último Los Santos, el ajuste encontró 6,76097 / −72,93003, profundidad hipotética 182 km, RMS 0,59 s y cambio máximo de 23,21 km al retirar una estación. La solución anterior de cuatro onsets estaba a 18,43 km del SGC. **No se demostró una mejora de exactitud:** seis hipótesis y RMS pequeño pueden producir una ubicación peor. Éste es precisamente un motivo para no publicar el ajuste automáticamente.

Los cuatro avisos compatibles con teleseísmos quedaron entre los nueve de datos insuficientes; no se convirtieron en ubicaciones colombianas aceptadas. Esto no prueba el rechazo de todos los teleseísmos posibles.

Se reprodujo además la grabación ambiental del 24 de agosto, de unos cinco minutos, examinando dos ventanas de búsqueda separadas. Ninguna reunió hipótesis para una ubicación. Es una comprobación puntual, no una estimación de falsos positivos por día ni un ensayo continuo de larga duración. No se emitieron ni inyectaron eventos.

## Verificación

- Suite completa del repositorio correcta antes de añadir el último test de límites del modelo; pruebas específicas repetidas sobre el estado final.
- Pruebas de fuente sintética independiente: ajuste P/S con ruido, estación perturbada, frente plano, P sin S, datos inválidos, falta de tiempos tabulados, límite de observaciones, límite de malla, revisión progresiva, aislamiento de eventos y expiración.
- `ruff src tests` y `mypy src` correctos en el estado final.
- Estos ensayos comprueban el software y sus rechazos; no validan precisión científica.

Resultados y caché local: `work/audits/seedlink-2026-10-24/epicenter-shadow-replay.json`, `epicenter-shadow-replay.log`, `location-nine-stations.mseed`. Las ondas no se agregan a Git.

## Próxima etapa necesaria

1. Revisar las hipótesis P contra anotaciones independientes y mejorar su identificación. El caso de Los Santos muestra que más hipótesis no garantizan mejor resultado.
2. Extraer y contrastar hipótesis S usando componentes horizontales y comprobar que pertenecen al mismo evento. El motor ya acepta pares P/S, pero el replay actual usa sólo el picker P existente.
3. Medir cobertura de incertidumbre y errores por región; extender ruido continuo y casos lejanos con un conjunto independiente reservado.
4. Conectar el cálculo progresivo al trabajador existente como telemetría experimental, con límites medidos de CPU y memoria, antes de cualquier cambio visible en la app. Preservar el centro de estaciones separado y la ubicación oficial aparte.

La primera etapa no habilita un epicentro propio fiable para los clientes ni cambia las compuertas que hoy mantienen los candidatos sin confirmar.

## Reproducción (PowerShell, desde el repositorio)

```powershell
python tools/review_epicenter_shadow.py --audit-dir ../audits/seedlink-2026-10-24 --deployed-source ../audits/seedlink-2026-10-24/production/detector/src --station-config ../../outputs/seismik/config.json --table ../../outputs/seismik/data/calibration/traveltime-iasp91-regional.npz --ambient-archive ../../outputs/seismik/data/replay/fixtures/co-2026-08-24-ambient.mseed --fetch
python -m pytest tests/test_epicenter_shadow.py -q
```

`--fetch` sólo descarga ondas si falta la caché. La herramienta lee el picker de la fuente desplegada recuperada por la auditoría; no lo importa de una rama diferente sin registrarlo. No realiza llamadas de escritura a producción.
