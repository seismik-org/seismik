# Acceso y latencia de estaciones centrales: implementación y resultado

Fecha: 17 de octubre de 2026. Alcance: interior de Colombia, sin ampliar a
estaciones extranjeras/periféricas.

## Resultado y límites de la implementación

Se implementó y probó `tools/audit_central_station_access.py`, una herramienta
pasiva para verificar inventario y recepción real, calcular **media aritmética**,
mediana, P95, máximos, huecos, solapamientos y muestras no finitas. No ejecuta
STA/LTA, no publica candidatos, no activa estaciones y no emite notificaciones.

**No se incorporaron estaciones nuevas.** Las únicas señales del interior
recibidas en esta prueba, HEL y RUS, ya estaban integradas. PRA y ROSC no estaban
anunciadas por el servidor público consultado; no se inventan latencias para ellas.
No se puede completar una integración nueva sin acceso a señales del operador.

## Mediciones observadas

Servidor: `rtserve.earthscope.org:18000`.

- GCP: trabajo temporal de Cloud Build en `us-east1`, 22:35:25–22:37:28 UTC
  (17:35:25–17:37:28 en Bogotá). Ventana solicitada: 120 s.
- PC: 22:31:13–22:33:15 UTC (17:31:13–17:33:15 Bogotá), también 120 s.
- No son ventanas simultáneas. Cloud Build no es el proceso Cloud Run productivo:
  estas mediciones no se atribuyen directamente a la latencia de producción.
- Atraso = hora UTC de recepción menos hora de la última muestra del paquete.
  No equivale a tiempo de origen del sismo, tiempo de detección o entrega al S21.

| Código técnico NSLC | Ubicación del metadato FDSN | Paquetes GCP | Media GCP | P95 GCP | Media PC | Viabilidad actual |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| CM.HEL.00.HHZ | Santa Helena, Medellín, Antioquia | 19 | 11,082 s | 19,828 s | 10,348 s | Recibe; ya integrada; esta prueba no pasa el objetivo de transporte rápido |
| CM.RUS.00.HHZ | La Rusia, Boyacá | 26 | 10,197 s | 18,848 s | 10,600 s | Recibe; ya integrada; esta prueba no pasa el objetivo de transporte rápido |
| CM.PRA.00.HHZ | Prado, Tolima | 0 | No medida | No medido | No medida | Bloqueada: sin stream anunciado en la ruta consultada |
| IM.ROSC..BHZ | El Rosal, Cundinamarca | 0 | No medida | No medido | No medida | Bloqueada: sólo metadatos, sin stream anunciado |

En las trazas recibidas no se observaron huecos, solapamientos ni muestras no
finitas durante la prueba corta. Sin embargo, HEL llegó a 19,828 s y RUS a
19,433 s de atraso máximo. Una media no demuestra suficiencia para aviso temprano:
ambas excedieron el umbral de 15 s en algunos paquetes. No se elevó esa compuerta
ni se apagaron sus diagnósticos existentes.

Las instantáneas previas de salud del último paquete (estudio anterior) y una
media de **todos** los paquetes recibidos en estas otras ventanas/conexiones no
son estadísticas intercambiables. No se atribuye toda la demora a la estación:
faltaría separar adquisición, empaquetado, proveedor y lector.

Las coordenadas/nombres se verificaron mediante la consulta FDSN `level=station`
de EarthScope para CM/IM y HEL/RUS/PRA/ROSC; IM.ROSC no se confunde con un antiguo
canal de la misma ubicación bajo código de red CM.

## Prueba temporal en GCP y control de calidad

Trabajo final: `0ecb117d-b2b0-4ddb-abd4-e922e28f20c4`, estado SUCCESS. Se ejecutó
solamente el auditor, usando la imagen ya existente del detector, sin iniciar
el detector ni construir/publicar imágenes nuevas. El contexto contenía dos
archivos de código/configuración, sin secretos ni ondas.

**Salvedad del cierre:** el resultado de GCP conserva `worker_stopped=false`:
el hilo lector seguía vivo al vencer los tres segundos de gracia. La toma de
muestras ya estaba detenida mediante la marca de fin, y el proceso/contenedor
terminó al concluir el trabajo. Las medias anteriores son observaciones
descriptivas, no una calificación completa. El registro conserva este hecho y
`qualification_complete=false`; no se reescribe el flag para aparentar éxito.
El auditor final interrumpe también el socket al cerrar y tiene una regresión
específica. No se ejecutaron más trabajos GCP para inflar confianza estadística.

Se descartaron intentos preliminares del auditor por cierre prematuro del lector.
Se separó la consulta INFO de la sesión de datos y se corrigió la confusión
entre timeout de `collect()` y edad admisible de una muestra. Un primer trabajo
GCP se canceló; otro falló al intentar escribir en `/workspace` con usuario sin
privilegios. El trabajo final escribió en `/tmp`. Esos intentos no se usan como
medición ni como evidencia de que las estaciones estuviesen caídas.

## Qué quedó implementado

- Selección exacta por red, estación, ubicación y canal; sin sumar espejos como
  sensores independientes. Ubicación vacía y ubicación `00` se distinguen.
- Sólo se solicitan streams anunciados; metadatos sin señal no producen latencia
  cero ni activación implícita.
- Media aritmética distinta de la mediana; se conservan P95, máximo y tamaño de
  muestra. Una muestra pequeña, reloj negativo, NaN o cierre prematuro no califica.
- Muestreo acotado por tiempo y memoria, sin retener formas de onda ni usar
  credenciales de consumo de Seismik.
- Registro reproducible en `data/stations/central-colombia-access-2026-10-17.json`,
  con ambas perspectivas y la salvedad de cierre del trabajo GCP.
- Pruebas unitarias/integración del auditor y regresiones de sesiones separadas,
  timeout de lectura y cierre del socket. Suite completa: 732 pruebas aprobadas;
  ruff en verde y mypy sin problemas en 83 archivos fuente.

## Lo que falta para una integración nueva y útil

Para UNAL/BT, OSQ u otro operador central se necesita un endpoint de intercambio
autorizado y operativo (host/puerto SeedLink o servicio equivalente), los NSLC
exactos y StationXML vigente. Las páginas institucionales demuestran actividad,
no conceden acceso ni ofrecen por sí mismas una URL de ondas utilizable.

Tras recibir acceso: medir continuidad y latencia desde el entorno productivo,
ruido día/noche, reloj, saturación, acoplamiento, geometría y eventos/negativos.
No se promete cubrir Bogotá–Meta o el Eje Cafetero con HEL y RUS, y no se añade
periferia para aparentar cobertura. La ML sigue `failed_validation` con su
autorización beta anterior: no se cambia evaluación ni CRITERIA.

Fuentes institucionales comprobadas para los siguientes acuerdos técnicos:
[UNAL, Instrumentación Geofísica](https://ciencias.bogota.unal.edu.co/laboratorios/geociencias/instrumentacion_geofisica/),
[FDSN BT](https://www.fdsn.org/networks/detail/BT/),
[FDSN UX](https://www.fdsn.org/networks/detail/UX/), y
[Observatorio del Quindío, actividad de 2026](https://www.uniquindio.edu.co/noticias/publicaciones/7163/en-la-uniquindio-convertimos-el-conocimiento-en-resiliencia/).

No hubo cambios en servicios Cloud Run, configuración productiva, alertas,
suscriptores ni calibración. No se hizo push ni despliegue de estaciones nuevas.
