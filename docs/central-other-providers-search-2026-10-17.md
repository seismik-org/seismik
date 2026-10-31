# Otros proveedores para las zonas ciegas centrales

Fecha: 17 de octubre de 2026. Búsqueda adicional posterior al primer auditor.

## Resultado

Se encontraron nuevos **metadatos de 52 códigos de estación Raspberry Shake**
(60 canales verticales) en el rectángulo central 2–8° N, 77,5–71° O. No se ha
demostrado que sean 52 sensores físicos independientes, activos o accesibles.
No se incorporó ninguna estación nueva al detector. No hubo despliegues,
cambios de alertas, compras, contactos a terceros ni trabajos nuevos en GCP.

La limitación nueva importante no es la latencia de HEL/RUS: para los candidatos
nuevos falta una ruta de datos autorizada y compatible con el uso de Seismik.
No se midieron paquetes de AM y, por tanto, su latencia es **null/no medida**.
No se usa el archivo retrasado como si fuese señal en vivo.

## Búsqueda instrumental realizada

Se consultaron canales verticales `??Z`, sin limitarse a HHZ, con metadatos cuya
época se extiende al 17 de octubre. Se usó timestamp completo para compatibilidad
con NCEDC/SCEDC. Servicios consultados:

EARTHSCOPE, GEOFON, BGR, BGS, EPOSFR, ETH, ICGC, INGV, IPGP, KNMI, KOERI,
LMU, NCEDC, NIEP, NOA, NRCAN, RESIF, RASPISHAKE, SCEDC, UIB-NORSAR, USP y
AUSPASS: **22 servicios**, no necesariamente 22 operadores independientes
(EPOSFR/RESIF son el mismo centro). AUSPASS tuvo un timeout en la repetición;
la consulta de seguimiento respondió 204. Los otros servicios sin resultados
también respondieron 204, no se les atribuye una caída por ello.

EarthScope devolvió los cuatro códigos físicos ya conocidos (HEL/PRA/RUS/ROSC),
además de VE.CAPV (Venezuela, excluida por alcance) y 18 canales SY sintéticos.
**SY no representa nuevos sensores físicos** y no se añade a detección.
Raspberry Shake fue el único catálogo adicional con candidatos centrales.

Se consultó también el catálogo federado geográfico de EarthScope para el
16–17 de octubre: sólo devolvió EarthScope y Raspberry Shake. El enrutador EIDA
respondió 204 para la misma zona/ventana. Son comprobaciones de catálogo/rutas,
no pruebas de telemetría ni una demostración de que no exista una red privada.

## Otros servidores de transmisión comprobados

Consultas pasivas INFO STREAMS a endpoints publicados, sin barrido de puertos:

| Operador/ruta | Resultado observado |
| --- | --- |
| USP `seisrequest.iag.usp.br:18000` | 52 estaciones anunciadas; ningún canal central encontrado |
| BGR `eida.bgr.de:18000` | 200 estaciones; ningún candidato central coincidente |
| IPGP `rtserver.ipgp.fr:18000` | 142 estaciones; ningún candidato central coincidente |
| EPOS-France `rtserve.resif.fr:18000` | 476 estaciones; ninguna de CM/IM/BT/UV/UX ni descripción Colombia |
| UFRN `sislink.geofisica.ufrn.br:18000` | Timeout de conexión desde este PC; no se afirma que la red esté apagada |
| UnB `datasis.unb.br:18000` | Timeout de conexión desde este PC; sin acceso demostrado |

Un aviso de mantenimiento mencionaba `rts.resif.fr`, que no resolvió. Se siguió
después la [documentación oficial vigente](https://seismology.epos-france.fr/real-time-seedlink/)
hasta `rtserve.resif.fr`; sí respondió. No se cerró esta vía por el primer fallo.
Tampoco se confundieron estaciones AM europeas de BGR/IPGP con Colombia.

Los inventarios fueron consultados aproximadamente entre 22:49 y 22:54 UTC,
17:49–17:54 en Bogotá. Esta búsqueda no genera nuevas estadísticas de latencia
de estaciones centrales porque no encontró una ruta nueva autorizada con datos.

## Candidatos nuevos con interés geográfico

Las áreas siguientes se infieren aproximadamente de coordenadas públicas:
no identifican al propietario, el emplazamiento exacto ni su estado operativo.

| NSLC | Área aproximada | Latencia media | Estado |
| --- | --- | --- | --- |
| AM.R15DD.00.EHZ / AM.RB143.00.EHZ | Armenia, Quindío | No medida | Acceso/acuerdo requerido; no contar como dos sensores independientes sin verificar |
| AM.R6789.00.EHZ | Entorno de Restrepo, Meta | No medida | Prioridad por hueco oriental; sin ruta autorizada |
| AM.R5661.00.SHZ | Bogotá | No medida | Metadatos, no recepción en vivo |
| AM.R78B7.00.SHZ | Sabana occidental, Cundinamarca | No medida | Metadatos, no recepción en vivo |
| AM.R9B6B.00.EHZ | Entorno de Ubaté, Cundinamarca | No medida | Metadatos, no recepción en vivo |
| AM.R1ADD.00.EHZ | Entorno de Neiva, Huila | No medida | Metadatos, no recepción en vivo |
| AM.R3B9B.00.EHZ / ENZ | Entorno de Cali, Valle | No medida | Dos canales de un código, no dos estaciones |

Registro completo: `data/stations/central-other-providers-2026-10-17.json`.
Todos los candidatos tienen `enabled=false`, permisos sin confirmar, cero
paquetes medidos y latencia null. El detector no consume este registro de
investigación: no se presenta como una integración activa.

## Condiciones de Raspberry Shake comprobadas

La [licencia pública del proveedor](https://raspberryshake.org/license/)
distingue acceso a datos y servicio de transmisión. El servicio central CAPS
para terceros requiere cotización; FDSN ofrece archivos de 30 minutos o más de
antigüedad y no sirve como flujo de aviso temprano. Las condiciones publicadas
restringen la integración comercial en plataformas web/móviles y la
redistribución digital, incluso para clientes que pagan. El proveedor también
advierte que la red comunitaria no está destinada a alertas de protección de
vidas. No basta pagar canales para dar por permitido Seismik o Waves.

Antes de integrar se necesita un acuerdo escrito que cubra específicamente
recepción para cálculo/alertas derivadas, y por separado cualquier almacenamiento
o redistribución de ondas. Alternativamente, un acuerdo directo con propietarios
para transmisión propia, con aclaración de derechos/licencias del equipo y de los
datos. No se asumió ninguna autorización ni se intentó extraer señales del visor.

## Operadores locales investigados además de UNAL/BT y OSQ

- **REDSW / Universidad del Valle, UV:** su página pública de sismograma enlaza
  un iframe de YouTube; no publica ahí una API de formas de onda. El enlace al
  mapa de estaciones devolvió 404. El acceso HTTPS desde Python falló por cadena
  de certificado; no se desactivó su verificación. El contenido institucional sí
  se consultó mediante el buscador. No se infirió un endpoint privado del vídeo.
  [Página institucional](https://osso.univalle.edu.co/sistema_de_analisis_de_datos_sismologicos/sismograma-digital-de-la-red-sismologica-del-suroccidente-colombiano.html).
- **SIATA:** documentación operativa institucional confirma adquisición
  instrumental con slarchive/SeedLink. Confirma que existe una red, no que su
  receptor esté abierto a terceros. No se encontró un endpoint público de ondas
  con autorización de incorporación.
  [Documento del operador](https://siata.gov.co/ingenieria_sismica/documentacion/CCT_016_2024/Anexos_Mensuales/Septiembre_2024/Manual_Encendido_Servidor_nazca.pdf).
- **RAMAN / UNAL Manizales–Corpocaldas:** se encontraron fichas públicas, por
  ejemplo La Nubia (`170010310076`) y El Cable (`170010310071`). Son códigos
  administrativos, no NSLC inventados. Una nota institucional de 2026 describe
  diez puntos y transmisión hacia una central; no ofrece un endpoint público.
  No se afirma que una ficha histórica pruebe actividad o telemetría actual.
  [Información institucional](https://manizales.unal.edu.co/index.php/noticias/unal-manizales-activa-sus-capacidades-para-apoyar-la-respuesta-ante-la-emergencia/).

## Punto de parada y siguiente paso concreto

Se agotaron las rutas públicas documentadas y verificables encontradas en esta
búsqueda ampliada. **No se demuestra que no haya más estaciones; no se encontró
otra que podamos incorporar ahora con señal y permiso comprobados.** No se
añadieron extranjeros/periferia ni se rebajaron compuertas para aparentar éxito.

El bloqueo ya requiere respuesta externa: acuerdo y endpoint de un propietario
de AM, REDSW, SIATA, RAMAN, OSQ o UNAL/BT. Para el primer acceso se requieren
host/protocolo/puerto autorizados, NSLC, StationXML vigente, respuesta instrumental,
sitio/acoplamiento y alcance de uso. Priorizar Meta y Quindío en AM y la vía
RAMAN/OSQ para el Eje Cafetero. Después se puede medir señal real y efectuar
ensayos independientes antes de usarla como entrada de aviso. No se realizó
ningún envío de correo ni se contrató un servicio en nombre del propietario.

## Evidencia reproducible local

En `work/station-survey-20261017/` del workspace padre:
`expanded_providers.py`, `expanded-providers.json`,
`expanded_live_inventory.py`, `expanded-live-inventories.json`,
`followup_discovery.py`, `expanded-followup.json` y
`build_expanded_registry.py`. Las consultas son acotadas; no almacenan ondas,
no publican eventos y no contienen credenciales.
