# Consolidación de workers — 2026-10-11

## Cambio aplicado en producción

- Dispatcher e integraciones + reenviador Pub/Sub en una instancia, 1 vCPU / 768 MiB.
- Primera revisión comprobada: `seismik-dispatcher-00055-scl`, tráfico 100%.
  Revisión final sana: `seismik-dispatcher-00056-z4b`, tráfico 100%, con un
  comando explícito al supervisor como compuerta de seguridad frente a imágenes
  antiguas desplegadas por CD.
- Reenviador separado: mínimo cero, revisión `seismik-event-forwarder-00005-mmr`.
- Detector sin modificar: `seismik-detector-00004-xcj`.
- No se cambiaron políticas de push, cálculo ML, secretos ni sus valores.
- Los procesos tienen sus propios puertos internos y entorno Python. Ambos deben
  estar sanos para que responda `/health/ready`; si falla uno, se reinicia la pareja.

Cloud Build `1e4a37f5-e7dc-41f3-90bf-4dfbd5f05fa7` construyó exclusivamente
las imágenes de producción fijadas por digest más el supervisor. La versión
local antigua del reenviador **no** se usó: no contiene el transporte ML beta.

## Verificación realizada

- Tres pruebas del supervisor y prueba de cancelación del worker combinado: pasan.
- Importación de ambos módulos y ruta `magnitude_estimate_update`: comprobadas
  durante el build, sin enviar eventos.
- Probes HTTP de arranque/liveness y GET autenticado del supervisor: `ok`.
- Salud de la API directa con secreto de origen sólo en memoria: `ready`.
- Pub/Sub `seismik-events-api`: backlog cero en la última muestra disponible.
- No se inyectaron eventos ni se probaron alarmas sobre usuarios reales.

El mínimo cero elimina la reserva permanente del servicio antiguo, pero las
copias calientes pueden permanecer temporalmente. Verificar `instance_count`
antes de afirmar que ya no queda ninguna. La reducción aproximada del 25% del
gasto total es una proyección, no una comparación de facturas medida. Confirmar
con días completos comparables, considerando créditos/free tier y tráfico.

## Retorno

Primero recuperar el reenviador separado y esperar que esté listo:

```powershell
gcloud run services update seismik-event-forwarder --project seismik-15bbb --region us-east1 --min-instances 1
gcloud run services update-traffic seismik-dispatcher --project seismik-15bbb --region us-east1 --to-revisions seismik-dispatcher-00054-6d2=100
```

Los exports locales previos están fuera del repo, en
`work/cost-rollback-20261011`, con referencias a Secret Manager, no valores de
credenciales. No borrar las revisiones antiguas antes de terminar la observación.

## Próximo CD

`Dockerfile.combined-worker` y `.github/workflows/ci.yml` tienen preparado el
supervisor y el mínimo cero del reenviador. Estos cambios **están locales, no
publicados**. Antes del próximo despliegue por GitHub deben integrarse sobre el
HEAD remoto actual; no hacer push del clon antiguo ni sobrescribir cambios del
otro PC. Cloud Run conserva un comando explícito `python /app/worker_supervisor.py`:
una imagen antigua sin ese archivo falla su arranque y no reemplaza la revisión
sana. El CD necesita este parche para volver a desplegar con éxito. No eliminar
esa compuerta hasta que se haya integrado el Dockerfile actualizado.

El digest fijado del reenviador requiere actualización explícita cuando cambie
su implementación. No reconstruirlo desde fuentes que no tengan ML beta.
