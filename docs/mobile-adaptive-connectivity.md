# Epicentro local y conectividad adaptativa — Android / iOS

## Presentación del epicentro

`place` sigue guardando la atribución original. Todas las vistas de detalle,
historial, selección para reportar, familia, marcadores y alarma dentro de la app
usan `displayPlace`: calcula la referencia desde las coordenadas en Colombia.
La notificación local crítica de Android utiliza también ese formateador.

El catálogo incluido contiene 1190 referencias (incluye variantes de nombres),
no 1190 municipios oficiales. Procede del snapshot de GeoNames existente en el
proyecto: GeoNames, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/),
[fuente](https://www.geonames.org/), generado el 2026-10-04; SHA-256 de la entrada:
`9d4b82b6de0ea929a7ba004a8e878fb97a49ee94bb792163db7e1ca85ac22ceb`.
Se adaptó el catálogo a tablas locales Dart/Swift. No se pide geocodificación a
Google/Apple ni se hace otra llamada de red por sismo.

No se confunde una cabecera municipal con límites administrativos: a más de
3 km se indica distancia y rumbo **desde** la población de referencia. Se usa
una referencia cercana (máximo 30 km para fuentes generales; hasta 120 km para
SGC/Colombia). Sin referencia fiable se conservan las coordenadas o se adapta
el texto disponible, sin inventar un municipio. Fuera de Colombia se normalizan
direcciones, «near/of», separadores y mayúsculas; no hay geocodificador mundial
offline. Sin coordenadas ni texto se muestra «Epicentro en revisión».

## Transporte

Se utilizan endpoints existentes: no requiere desplegar una API nueva ni
cambiar claves, Firebase, políticas de push o el cálculo de magnitudes.

- Arranque: solicita hasta 50 eventos, en vez de 200.
- Dos transferencias rápidas: hasta 200 eventos.
- Fallo de transporte, respuesta 429/5xx o transferencia >=5 segundos: hasta
  30 eventos, sin reducir el umbral de magnitud ni cambiar las fuentes elegidas.
- Tres transferencias rápidas consecutivas recuperan el perfil completo.
- `Accept-Encoding: gzip`: utiliza compresión de respuesta si el servidor/CDN
  la ofrece; el cliente HTTP/URLSession descomprime. No se comprime ni modifica
  el cuerpo firmado de los reportes: conserva HMAC y el `report_id` idempotente.
- Solicitudes de historial/reportes toleran una conexión lenta (25/40 s según
  perfil); el cliente Android espera hasta 20 s para establecer conexión.
- Reportes pendientes y recuperación de alertas van antes del catálogo de
  estaciones. En modo lento el catálogo se lee de caché, no se descarga.
- Caché de estaciones iOS: 12 horas; Android ya tenía la misma política.
- En modo lento se pospone el mapa del monitor; la persona puede cargarlo
  expresamente. Los mapas abiertos expresamente, incluido el del detalle,
  siguen dependiendo del proveedor y no tienen garantía de mapas offline.
- Actualización automática **sólo en primer plano**: 60 s normales / 180 s
  limitados, sin descargas simultáneas del historial. Al volver a la app o tirar
  para actualizar sigue siendo inmediata. Push permanece independiente de
  este intervalo; no se retrasa la emisión de alertas.
- Las últimas respuestas correctas y los reportes encolados sobreviven a
  reinicios. Una copia offline no se presenta como sincronizada.

30 frente a 200 reduce el máximo de eventos transmitidos un 85%, no garantiza
un 85% menos bytes: las estaciones, metadatos, TLS, tamaño variable de eventos
y compresión también influyen. No hay protocolo SMS/satelital ni garantía de
entrega instantánea con 2G/3G congestionada o infraestructura móvil caída.

## Verificación

`flutter test --no-pub`: 160 pruebas pasaron, incluidas calidad/degradación,
historial ligero, compresión solicitada, autenticación intacta, nombres locales,
atribución preservada, cola offline y concurrencia de sincronización.
Hay pruebas XCTest equivalentes para resolución de epicentro y calidad. Xcode
y pruebas nativas de iOS necesitan un Mac/runner de GitHub; no se ejecutaron en
este Windows. La prueba real con latencia/pérdida de paquetes y los teléfonos
del piloto aún es necesaria antes de prometer tiempos de entrega.

No se publicó en Play Store/TestFlight ni se desplegaron servicios durante
esta tarea. El cambio de apps debe incluirse en el próximo build.
