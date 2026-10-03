# Planes por cuenta de desarrollador

El catálogo público en `/v1/developer/config` contiene Always Free,
Pay-as-you-go, Pro, Max, Ultra y Enterprise. El endpoint público sin clave
sigue separado. Precios USD antes de impuestos; los cobros están desactivados.

| Plan | Precio | Minuto / día / mes / claves |
| --- | --- | --- |
| Always Free | US$0 | 60 / 10.000 / 30.000 / 3 (minuto, día y claves configurables) |
| Pay-as-you-go | saldo US$5, US$25 o US$100; eventos US$0,0005 y estaciones US$0,001 por consulta | 120 / 20.000 / 200.000 / 5 |
| Pro | US$19/mes | 120 / 10.000 / 50.000 / 5 |
| Max | US$49/mes | 240 / 20.000 / 150.000 / 10 |
| Ultra | US$129/mes | 360 / 40.000 / 400.000 / 20 |
| Enterprise | acuerdo personalizado | acordadas; sin overrides usa límites gratuitos finitos |

Las suscripciones incluyen consultas de ambos productos dentro de sus cuotas;
no se aplican tarifas Pay-as-you-go automáticamente. Al superar cualquier
cuota la API devuelve 429. Los días reinician a las 00:00 UTC y los meses el
día 1 a las 00:00 UTC; no se acumulan consultas sin usar. Cambiar el plan no
reinicia el medidor. El cupo mensual se reserva atómicamente entre claves y
workers. Free no descuenta saldo; Pay-as-you-go tampoco lo descuenta durante
la beta: el débito comercial y el checkout están pendientes de integración.

`POST /v1/developer/plan-selection` exige identidad del propietario y recibe
`plan_id`. Guarda `selected_plan_id` en su perfil y `/account` lo devuelve.
Elegir un plan no concede cuotas, activa una suscripción ni cobra. El portal
muestra la selección persistente y el contacto para acordar la activación.
El identificador interno `pay_as_you_use` se conserva por compatibilidad con
las cuentas existentes; su nombre público ahora es Pay-as-you-go.

Polar almacena el catálogo comercial; hasta integrar y probar webhooks firmados,
renovaciones, cancelaciones y conciliación, el portal NO ofrece checkout. Crear un
producto no habilita pagos ni convierte una cuenta en un plan de pago. Los límites se suman
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
python -m api.developer_plans UID_VERIFICADO pro --actor ADMIN_IDENTIFICADO --reason "Piloto aprobado" --requests-per-minute 120 --requests-per-day 10000 --requests-per-month 50000 --max-active-keys 5
```

No usar un correo como UID salvo que ese sea realmente el identificador de la
sesión. La operación se registra en `stream:seismik:developer-plan-audit`. Redis
necesita persistencia y respaldos: no sustituye una futura base contractual.
Al reasignar un plan se eliminan límites especiales anteriores; volver a `free`
restaura las cuotas gratuitas. Las claves ya existentes no se revocan por un
cambio de plan, pero la cuenta no puede crear nuevas sobre el límite activo.

El desarrollo local no equivale a un despliegue: publicar frontend y backend
juntos para que `/account` y el catálogo estén disponibles antes de usar la UI.
