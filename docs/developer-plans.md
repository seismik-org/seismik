# Planes por cuenta de desarrollador

El catálogo público en `/v1/developer/config` contiene Always Free with API Key,
Pay-as-you-use, Pro y Enterprise. El endpoint público sin clave sigue separado.
Pro cuesta US$19/mes y Enterprise se negocia. Ningún cambio activa pagos.

| Plan | Precio antes de impuestos | Minuto / día / claves |
| --- | --- | --- |
| Always Free | US$0 | 60 / 10.000 / 3 (configurable por despliegue) |
| Pay-as-you-use | saldo US$5, US$25 o US$100; eventos US$0,0005 y estaciones US$0,001 por consulta | 120 / 20.000 / 5 |
| Pro | US$19/mes, consultas incluidas dentro de cuotas | 120 / 20.000 / 10 |
| Enterprise | acuerdo personalizado | acordadas, nunca ilimitadas por defecto |

Polar almacena el catálogo comercial; hasta integrar y probar webhooks firmados,
renovaciones, cancelaciones y conciliación, el portal NO ofrece checkout. Crear un
producto no habilita pagos ni convierte una cuenta en Pro. Los límites se suman
entre todas las claves de la cuenta y los diarios reinician a las 00:00 UTC.

`GET /v1/developer/account` exige sesión del portal o identidad Firebase verificada.
Devuelve solamente el plan y consumo del usuario autenticado; no permite elegir
otro UID ni modificar planes. Las cuentas existentes y nuevas sin asignación
administrativa usan `free`. El registro autoritativo es el perfil Redis de la
cuenta; todas sus claves reflejan ese plan, incluso las emitidas antes del cambio.

Las cuotas por minuto y día se comparten entre las claves de una cuenta. El
inventario conserva también el consumo de cada clave. Los planes activados
administrativamente usan sus cuotas publicadas salvo límites expresamente
acordados. La selección del catálogo no concede privilegios ni abre un checkout.

## Activación administrativa

Ejecutar sólo en un entorno administrativo con el Redis correcto configurado,
tras confirmar las condiciones con el cliente. Ejemplo, no ejecutar a ciegas:

```powershell
$env:PYTHONPATH = "src"
python -m api.developer_plans UID_VERIFICADO pro --actor ADMIN_IDENTIFICADO --reason "Piloto aprobado" --requests-per-minute 120 --requests-per-day 20000 --max-active-keys 5
```

No usar un correo como UID salvo que ese sea realmente el identificador de la
sesión. La operación se registra en `stream:seismik:developer-plan-audit`. Redis
necesita persistencia y respaldos: no sustituye una futura base contractual.
Al reasignar un plan se eliminan límites especiales anteriores; volver a `free`
restaura las cuotas gratuitas. Las claves ya existentes no se revocan por un
cambio de plan, pero la cuenta no puede crear nuevas sobre el límite activo.

El desarrollo local no equivale a un despliegue: publicar frontend y backend
juntos para que `/account` y el catálogo estén disponibles antes de usar la UI.
