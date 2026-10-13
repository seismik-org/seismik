# Un sismo, varias fuentes

`GET /v1/events/history` agrupa reportes oficiales de fuentes distintas con
hora de origen a ≤45 segundos, epicentros a ≤40 km y, cuando ambas fuentes
dan profundidad, diferencia a ≤60 km. Es una asociación conservadora de
catálogos, no validación científica ni una decisión de alertamiento.

Todas las parejas del grupo deben cumplir los criterios y cada fuente puede
aportar un solo evento. Enjambres ambiguos, cadenas transitivas, eventos sin
hora/coordenadas válidas, preliminares y simulacros no se fusionan. La magnitud
no decide la coincidencia: escalas ML, Mw y mb pueden discrepar legítimamente.

El evento conserva los campos anteriores y un ID de fuente, con preferencia
SGC, USGS y EMSC para la representación principal; no se genera un promedio.
Se agregan `source_reports` (reportes originales completos),
`related_event_ids` y `association_method`. El ID principal puede cambiar si
se incorpora posteriormente una fuente preferida: los alias permiten reconocer
sus avisos anteriores. No se promete identidad persistente del catálogo.

El mínimo de magnitud se aplica al grupo después de asociar. Si una fuente
supera el umbral, se conservan también los reportes inferiores al umbral del
mismo evento. Límite y caché se aplican a eventos agrupados. GeoJSON conserva
estas propiedades. Errores parciales de fuentes siguen en el contrato original.

Android y iOS mantienen estas fuentes en la copia sin conexión y ofrecen en
el detalle magnitud, escala, organización, estado de revisión y enlace oficial.
La selección para reportes ciudadanos usa un solo evento principal. Los avisos
recuperados reconocen alias para no reinsertar otra copia de una organización.

No se cambian dispatcher, push, Critical Alerts ni la magnitud experimental de
Seismik. Desplegar requiere reconstruir solo la API; los clientes requieren una
nueva entrega. Antes de desplegar, reconciliar el árbol de producción manual
con el clon: no sobrescribir cambios API de Claude o ML beta fuera de `main`.
