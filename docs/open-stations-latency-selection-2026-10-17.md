# Estaciones abiertas: medición y selección regional — 17 de octubre de 2026

> **Alcance sustituido por decisión del propietario el 17 de octubre:** no añadir
> estaciones periféricas ni extranjeras; concentrar la ampliación en el centro
> de Colombia. Las ocho candidatas de este informe quedan sólo como mediciones
> históricas, fuera de la selección vigente. Nunca se activaron en producción.
> El manifiesto vigente deja `new_trial_stations=[]` y conserva los datos en
> `historical_peripheral_candidates_not_selected`. Véase
> [plan central actualizado](central-colombia-station-plan-2026-10-17.md).

## Resultado

Se encontraron ocho estaciones adicionales con trazas verticales continuas,
respuesta instrumental abierta y retraso de transporte inferior a 15 s durante
pruebas de dos a cuatro minutos: EC.ANTS, EC.CHSH, EC.PULU, EC.PUYO, IU.OTAV,
CU.BCIP, OV.VPCC y TC.DRK0. Se seleccionan para una **prueba de adquisición pasiva**, no para
activar alertas ni declarar buena cobertura nacional. La configuración de
producción y las alertas personales permanecen intactas.

El transporte público permite mejorar la geometría potencial en algunas zonas,
pero no se encontraron señales nuevas suficientes para cerrar los huecos del
interior de Colombia. No se rebajaron el quórum, la compuerta de 15 s ni los
criterios científicos. La ML sigue sin validación científica.

## Método y límites

- Inventarios públicos SeedLink `INFO STREAMS`, cruzados por NSLC exacto con
  metadatos FDSN de canales vigentes. Un catálogo de estaciones no prueba que
  lleguen datos en vivo.
- Una conexión multicanal por servidor en cada prueba; no una por estación.
  No se inyectaron eventos, no se enviaron alertas y no se guardaron ondas.
- Retraso = UTC de recepción menos tiempo de la última muestra del paquete.
  **No** es tiempo desde el origen del terremoto ni entrega de notificaciones.
- La prueba principal se hizo desde el PC, 19:06:11–19:10:12 UTC
  (14:06:11–14:10:12 de Bogotá), 240 s. Se conservan estadísticas de todos los
  paquetes y, por separado, del tramo posterior a los primeros 60 s.
- La comprobación adicional de Costa Rica fue 22:11:31–22:13:31 UTC
  (17:11:31–17:13:31 de Bogotá), 120 s. No es simultánea a la prueba principal.
- Los primeros intentos con un error local de importación y con un selector
  incorrecto para ubicaciones SEED vacías no se usan para declarar estaciones
  caídas. La repetición usa `HHZ` para ubicación vacía, `00BHZ` para ubicación
  `00` y filtra el NSLC exacto al recibir.
- No son pruebas de disponibilidad prolongada, sensibilidad, ruido sísmico,
  magnitud, localización real ni anticipación útil. Tampoco sustituyen medir
  estas rutas desde la región de producción.

## Selección principal

Todas las siguientes rutas fueron medidas por `rtserve.earthscope.org:18000`.
Las cuatro EC y las dos de Costa Rica tienen 100 Hz, OTAV usa BHZ a 20 Hz y
BCIP BHZ a 40 Hz. StationXML confirma acceso `open`, sensibilidad positiva y
etapas de respuesta para los ocho NSLC exactos. No se añadieron a la calibración de ML.

| Estación / ubicación / canal | País real | Paquetes | Mediana | P95 | Función propuesta |
| --- | --- | ---: | ---: | ---: | --- |
| EC.ANTS / vacío / HHZ | Ecuador | 70 | 1,360 s | 1,853 s | Referencia sur |
| EC.CHSH / vacío / HHZ | Ecuador | 100 | 2,056 s | 2,873 s | Referencia sur/suroccidente |
| EC.PULU / vacío / HHZ | Ecuador | 68 | 1,475 s | 2,043 s | Referencia sur |
| EC.PUYO / vacío / HHZ | Ecuador | 72 | 1,541 s | 1,935 s | Referencia sureste del grupo ecuatoriano |
| IU.OTAV / 00 / BHZ | Ecuador | 12 | 5,643 s | 8,182 s | Referencia norte de Ecuador |
| CU.BCIP / 00 / BHZ | Panamá | 29 | 4,428 s | 10,658 s | Referencia noroccidental |
| OV.VPCC / vacío / HHZ | Costa Rica | 55 | 1,683 s | 2,292 s | Referencia para las islas; prueba adicional |
| TC.DRK0 / vacío / HHZ | Costa Rica | 33 | 5,056 s | 7,742 s | Referencia para las islas; prueba adicional |

En estas ocho trazas no se observaron huecos, solapamientos ni muestras no
finitas durante sus respectivas ventanas. Eso no garantiza continuidad fuera de ellas.
Otavalo HHZ estaba atrasado en el inventario: se escogió el BHZ vigente, no
se sumaron ambos canales como estaciones independientes.

La mediana no oculta extremos: el JSON conserva máximos, P95 y fracción de
paquetes dentro de 15 s. Aruba PR.ACPR se deja fuera de la selección rápida:
P95 16,191 s, aunque el nombre aparezca activo en el catálogo.

## Estaciones colombianas existentes y respaldo

Se conservan CM.ARGC, HEL, OCA, PRV, RUS, SMAR y URI. En 30 instantáneas del
detector en Cloud Run, 18:48:50–19:03:20 UTC, sus medianas del último paquete
estuvieron entre 2,746 y 4,860 s. OCA tuvo una instantánea con 15,573 s y sólo
29/30 saludables; las otras seis tuvieron 30/30. No es un porcentaje de
disponibilidad de largo plazo ni una distribución de todos los paquetes.

Desde el PC los mismos canales tuvieron P95 de 15,787–19,423 s. Las dos
perspectivas se presentan por separado: no se equipara una prueba del PC con
latencia en GCP y no se eleva la compuerta para aceptar paquetes viejos.

El servidor del Observatório Nacional, `rsis1.on.br:18000`, retransmite RUS y
URI. En 120 s se recibieron 4 y 6 paquetes respectivamente; medianas
11,382/11,490 s y P95 17,408/16,352 s. **No se habilita failover automático**:
la muestra es pequeña y supera la compuerta en algunos paquetes. Son rutas
alternativas de los mismos dos sensores, no dos estaciones nuevas ni dos
votos de quórum adicionales. Tampoco garantizan independencia del enlace de
origen del SGC.

## Geometría: mejora parcial, todavía no cobertura nacional

Se revisaron 24 puntos de referencia aproximados. Se cuentan estaciones
físicas a menos de 500 km y el hueco azimutal máximo, conservando la condición
actual de cuatro estaciones y hueco <=240°. Es un filtro **necesario, no
suficiente**. No se estima aquí tiempo de viaje, magnitud o aviso anticipado.

Comparación hipotética de las siete CM con esas mismas siete más las ocho
seleccionadas, suponiendo soporte regional transfronterizo:

| Punto de referencia | Estaciones <=500 km, antes → después | Hueco, antes → después | Lectura |
| --- | ---: | ---: | --- |
| Cali | 2 → 5 | 325,5° → 169,1° | Mejora geométrica potencial |
| Popayán | 1 → 5 | 360° → 183,6° | Mejora geométrica potencial |
| Neiva | 2 → 5 | 319,3° → 183,8° | Mejora geométrica potencial |
| Mutatá | 5 → 6 | 249,5° → 160,5° | BCIP aporta otro azimut |
| San Andrés | 1 → 4 | 360° → 155,5° | Mejor geometría potencial con Costa Rica |
| Bogotá | 3 → 3 | 275,9° → 275,9° | Sigue insuficiente |
| Villavicencio | 3 → 3 | 300,2° → 300,2° | Sigue insuficiente |
| Pasto | 0 → 5 | 360° → 325,2° | Varias estaciones, todas hacia el mismo lado |
| Tumaco | 0 → 5 | 360° → 343,4° | Sigue mala geometría |
| Florencia | 0 → 4 | 360° → 333,7° | Cuatro no bastan con esa distribución |
| Leticia / Puerto Carreño | 0 → 0 | 360° → 360° | Sin solución con esta selección |

No convertir el número de puntos que pasan en un porcentaje de territorio o
población. Estaciones a cientos de kilómetros pueden mejorar una localización
tardía sin permitir avisar antes de la sacudida cerca del epicentro.

## Fuentes descartadas o condicionadas

- GEOFON: NU.BLUN conserva datos terminados el 30 de junio y no entregó
  paquetes en la prueba. NU.ESPN sí entregó EHZ con mediana 0,756 s y P95
  0,922 s, pero no se encontró respuesta instrumental vigente para ese canal
  y ubicación exactos; además no resuelve los huecos del interior colombiano.
- IPGP: G.HDC corresponde al mismo sensor de Costa Rica visto por EarthScope.
  Sólo llegaron dos paquetes en 120 s: insuficiente para calificar una ruta.
- Brasil USP/ON: TBTG y TEFE aparecen sin streams; SGC2 conserva datos de
  septiembre de 2025 en USP. No contar ese catálogo como señal amazónica viva.
  Los dos nombres históricos del nodo UnB probados no resolvieron/conectaron.
- Venezuela: IU.SDV no estaba anunciada en EarthScope; en ON el BHZ más
  reciente terminaba el 14 de octubre. No es una referencia viva admisible.
- NU.SIUN: transmite a 100 Hz, pero el metadato publicado dice 0 Hz. Hay que
  conciliar respuesta y metadatos antes de usarla como entrada científica.
- TC.PIRO: el estado de restricción heredado en StationXML es `partial`, no
  se presenta como entrada científica completamente abierta.
- GeoShake: se encontró un sensor comunitario en Bogotá y se midió su LNZ
  (24 paquetes/90 s; mediana 2,884 s, P95 2,938 s). Es una envolvente positiva
  de 1 Hz de un MEMS sin calibración individual; no una onda vertical firmada
  continua. Sólo sería un complemento separado, nunca entrada de ML o picks
  P del detector actual. No se publica su ubicación precisa en este informe.
- Raspberry Shake: el acceso público no equivale a permiso de integración
  comercial y redistribución. Su licencia exige acuerdos específicos; no se
  eligió como fuente gratuita para Seismik/Waves.

## Obstáculos para integrar sin romper salvaguardas

1. El asociador desplegado devuelve `colombia_model_only` si una estación no
   tiene país CO. No se falsea el país de una estación ecuatoriana o panameña.
   Se necesita soporte regional probado que mantenga país de origen y use el
   hipocentro candidato para la política geográfica, no el centroide de la red.
2. Los filtros por país/zona también deben reconocer referencias fronterizas
   explícitas; simplemente añadirlas a `config.json` no basta.
3. La ML beta existente sólo admite su conjunto/calibración actual de CM. Una
   estación rápida con respuesta instrumental no queda calibrada para esa ML.
4. Antes de activar nuevas asociaciones: adquisición pasiva prolongada, medir
   desde GCP, revisar ruido, relojes, continuidad y CPU, y repetir pruebas de
   eventos y negativos sin publicar históricos ni activar push público.
5. Los huecos prioritarios requieren señales interiores: Bogotá–Meta/Llanos,
   Eje Cafetero–Tolima, Chocó, Cauca–Nariño, Caquetá y oriente/Amazonía.
   Priorizar recuperar CM.PRA/FLO2/TUM/CAP2/LCBC y convenios con operadores
   locales. La red BT de UNAL existe en FDSN, pero la consulta federada no
   devolvió un endpoint abierto utilizable; no se inventa uno ni se contacta
   a instituciones sin autorización.

## Evidencias y estado de cambios

El manifiesto `data/stations/colombia-open-selection-2026-10-17.json` distingue
primarias, propuestas y rutas condicionadas, con `auto_activation=false`.
Evidencia completa y scripts acotados en `work/station-survey-20261017`:
inventarios, latencias por paquete, StationXML y geometría. No contiene claves
ni tokens y no se guardaron trazas. No se modificó código de detección,
configuración de producción, push, ML/calibración ni despliegues. No hay push
a GitHub ni nuevos servicios de nube.

Fuentes primarias consultadas:

- [EarthScope SeedLink: acceso, límites y ausencia de garantías](https://docs.earthscope.org/service/seedlink).
- [IG-EPN: señales compartidas mediante IRIS/EarthScope](https://www2.igepn.edu.ec/senales-sismicas).
- [GEOFON: SeedLink abierto](https://geofon.gfz.de/waveform/seedlink.php).
- [GEOSCOPE/IPGP: ondas en tiempo real](https://geoscope.ipgp.fr/index.php/en/data/continuous-data/description).
- [USP: servicios y servidor SeedLink](https://sismo.iag.usp.br/rq/).
- [Procedimientos de los operadores brasileños, ISC](https://www.isc.ac.uk/iscbulletin/agencies/VAO-ops.pdf).
- [GeoShake: significado de LNZ y limitaciones instrumentales](https://map.geoshake.org/developer).
- [Licencia de Raspberry Shake](https://raspberryshake.org/license/).
- [FDSN: red BT de la Universidad Nacional](https://www.fdsn.org/networks/detail/BT/).
- [ShakeAlert: la distancia a estaciones condiciona la anticipación](https://www.shakealert.org/eew-research/caltech/infrastructure/).
