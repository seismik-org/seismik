# Ampliación centrada en el interior de Colombia — 17 de octubre de 2026

Búsqueda ampliada posterior: [otros proveedores y candidatos centrales](central-other-providers-search-2026-10-17.md).
Se encontraron 52 códigos AM en metadatos; no se activaron por falta de ruta
en vivo autorizada y condiciones de integración compatibles comprobadas.

## Decisión y estado

Por instrucción expresa del propietario, se retiran de la ampliación propuesta
las ocho estaciones extranjeras/periféricas del estudio anterior. No se habían
activado. Sus mediciones se conservan únicamente como antecedente, sin contar
como cobertura conseguida ni como candidatas vigentes. No se eliminan estaciones
existentes ni se alteran alertas, límites, ML o configuración de producción.

**Nuevas estaciones centrales calificadas: cero. Buena cobertura central:
todavía no demostrada.** No se afirma una garantía de cobertura o calidad que
los datos no sostienen.

Actualización posterior: se implementó el auditor de acceso y se hicieron pruebas
en el PC y en GCP; véanse [resultados de implementación](central-station-access-implementation-2026-10-17.md)
y `data/stations/central-colombia-access-2026-10-17.json`. Esto no añadió estaciones:
HEL/RUS ya existían y PRA/ROSC no ofrecieron un stream abierto verificable.

## Prioridad territorial

1. Bogotá–Cundinamarca–Meta: capital, piedemonte y ambos lados de la Cordillera
   Oriental, no solamente sensores al norte de Bogotá.
2. Caldas–Risaralda–Quindío–Tolima: Eje Cafetero y valle del Magdalena.
3. Huila–Valle del Cauca: completar el corredor centro-sur.
4. Antioquia–Boyacá–Santander: aprovechar HEL/RUS y cerrar huecos interiores.

Son corredores de búsqueda, no ubicaciones definitivas para instalar equipos.
La selección de un sitio requiere revisar geología, acoplamiento al suelo,
ruido, alimentación, reloj y comunicaciones. No se elige una sede sólo por estar
en una ciudad prioritaria.

## Comprobación pública de acceso

Consulta del 17 de octubre, **22:16:09 UTC / 17:16:09 Bogotá**. Enfoque operativo
aproximado: latitudes 2–8° N, longitudes 77,5–71° O. Es un rectángulo de búsqueda,
no un polígono de Colombia ni una definición exhaustiva de su región central.

Se cruzaron canales vigentes FDSN con inventarios SeedLink actuales de
EarthScope, GEOFON y Observatório Nacional de Brasil:

| Entrada | Lo comprobado | Decisión |
| --- | --- | --- |
| CM.HEL.00.HHZ | Canal anunciado en EarthScope, ya usado por Seismik | Conservar; no es nueva estación |
| CM.RUS.00.HHZ | Anunciado en EarthScope y ON, ya usado | Conservar; las dos rutas no son dos sensores |
| CM.PRA.00.HHZ | Metadato vigente en EarthScope, sin stream en los tres inventarios consultados | Prioridad para recuperar acceso; no calificada |
| IM.ROSC..BHZ, El Rosal | Metadato vigente en EarthScope, sin stream en esos inventarios | No confundir metadatos con acceso abierto en vivo |
| VE.CAPV..HHZ | Aparece en el rectángulo geográfico pero está en Venezuela | Fuera del nuevo alcance |
| BT, UX, UV | Consulta federada de cada red: HTTP 204; sin estaciones anunciadas de esas redes en los tres servidores | No hay un endpoint público operativo demostrado por esta comprobación |

GEOFON devolvió HTTP 204 para los metadatos del rectángulo. No se interpretan
esos resultados como prueba de que las redes no existan, estén apagadas o no
dispongan de acuerdos privados. Simplemente no proporcionan una nueva entrada
pública en vivo verificable a Seismik mediante las fuentes consultadas.

No se hizo barrido de puertos, no se intentó evitar restricciones y no se
contactó a operadores. No hay latencia que reportar para una señal no recibida;
se deja como no medida, nunca cero.

## Operadores que sí corresponden al objetivo

- **UNAL, Red Geofísica / BT:** la página institucional del Laboratorio de
  Instrumentación Geofísica confirma recepción y análisis de datos en tiempo
  real. FDSN registra BT. Son evidencias de operación/registro, no permiso de
  acceso ni prueba de que todos los sitios publicados en notas de 2017 sigan
  funcionando. Es el interlocutor prioritario para el corredor Bogotá–Meta–Tolima.
- **Observatorio Sismológico de la Universidad del Quindío:** una publicación
  institucional de 2026 confirma trabajo con registros instrumentales. Es una
  vía pertinente para el Eje Cafetero; no se encontró un SeedLink abierto medible.
- **UIS / REDNE, UX:** FDSN confirma la red regional; no apareció un endpoint
  abierto en la comprobación federada. Puede complementar el interior nororiental,
  pero no sustituir la cobertura de Bogotá o del Eje Cafetero.
- **SGC:** recuperar publicación/autorización para estaciones interiores como
  PRA sería útil. La presencia de una estación en su visor, en un informe o en
  FDSN no equivale a un canal disponible para Seismik.

El vínculo previo del proyecto con UniCaldas/UNAL puede facilitar la revisión
técnica y un eventual convenio. No se da por concedido ni se presupone que
UniCaldas opere una red abierta distinta del SGC.

## Qué debe demostrarse antes de calificar una estación nueva

1. Acceso público documentado o autorización del operador; uso y redistribución
   compatibles con el propósito concreto, especialmente si se incorpora a Waves.
2. NSLC único, coordenadas y orientación fiables, canal vertical continuo,
   respuesta instrumental vigente, unidades y frecuencia de muestreo coherentes.
   Una envolvente comunitaria de 1 Hz no sustituye una onda sísmica firmada.
3. Medir **desde la región de producción**, con una ventana pasiva que abarque
   día y noche. Objetivo de aceptación propuesto: al menos 72 h, P95 de atraso
   <=5 s y P99 <=10 s. Son objetivos operativos por revisar, no una garantía ni
   cambios a la compuerta productiva de 15 s. Un promedio bueno no oculta cortes
   o paquetes viejos.
4. Revisar continuidad y disponibilidad efectivamente observadas, saltos de
   reloj, solapamientos, saturación, ruido día/noche y eventos no sísmicos.
5. Demostrar geometría y tiempos de adquisición útiles **por corredor** y
   redundancia ante pérdida de estaciones. Cuatro estaciones a cientos de
   kilómetros no equivalen a una red de aviso temprano local.
6. Repetir ensayos independientes con sismos y ruido antes de afirmar mejoras
   de detección o aviso. La evaluación de ML y sus CRITERIA no se modifican para
   incorporar una estación; `failed_validation` no pasa a `validated` por disponer
   de más señales.

No se ha creado una monitorización programada ni se ha iniciado una campaña
de 72 h. Es una condición propuesta para una futura adquisición autorizada.

## Resultado práctico

Con las fuentes públicas comprobadas no se puede conseguir hoy una red central
de buena cobertura únicamente cambiando la lista de suscripciones. El siguiente
paso útil es obtener acceso medible de un operador interior y/o diseñar una red
local asociada, y entonces calificar sus señales. No se añade periferia para
inflar el número de estaciones.

Manifiesto vigente: `data/stations/colombia-open-selection-2026-10-17.json`.
Evidencia de consultas: `work/station-survey-20261017/central-colombia.json`.
No hay despliegues ni cambios en el código de detección por esta decisión.

## Fuentes primarias

- [UNAL: Laboratorio de Instrumentación Geofísica](https://ciencias.bogota.unal.edu.co/laboratorios/geociencias/instrumentacion_geofisica/).
- [UNAL: distribución histórica de la red, nota de 2017](https://agenciadenoticias.unal.edu.co/detalle/estaciones-portatiles-monitorean-actividad-sismica-de-la-sabana-de-bogota).
- [FDSN: BT](https://www.fdsn.org/networks/detail/BT/), [UX](https://www.fdsn.org/networks/detail/UX/), [UV](https://www.fdsn.org/networks/detail/UV/).
- [Universidad del Quindío: trabajo instrumental y resiliencia, 2026](https://www.uniquindio.edu.co/noticias/publicaciones/7163/en-la-uniquindio-convertimos-el-conocimiento-en-resiliencia/).
- [EarthScope: condiciones y limitaciones de su servicio SeedLink](https://docs.earthscope.org/service/seedlink).
