# Precios de lanzamiento — revisión del 2 de octubre de 2026

Precios USD antes de impuestos. Pro US$19/mes por 50.000 consultas,
Max US$49 por 150.000 y Ultra US$129 por 400.000. Son propuestas de
lanzamiento; no son tarifas justificadas por una medición marginal completa.
Pay-as-you-go conserva US$0,0005/eventos y US$0,001/estaciones,
con recargas US$5/25/100. Free tiene 30.000 consultas mensuales.

## Cómo se acota el cómputo

Las cuotas mensuales, diarias y por minuto se comparten entre todas las claves
de una cuenta. La reserva mensual usa WATCH/MULTI sobre el medidor Redis,
por lo que solicitudes concurrentes no multiplican la capacidad contratada.
Al superar una cuota se devuelve 429: no hay excedentes automáticos ni paso
implícito a pago por uso. Cambiar de plan no reinicia el consumo del mes.
Los meses son calendario UTC, sin acumulación; no existe aún un ciclo asociado
a una renovación de pago. Pay-as-you-go tiene 1.000.000 consultas/mes como
límite operativo beta, independiente del saldo. Enterprise requiere cuotas
acordadas; sin ellas usa límites gratuitos finitos.

La API de historial limita ventanas a 30 días y respuestas a 500 eventos,
y reutiliza caché y locks acotados. El catálogo de estaciones puede ser más
pesado y mantiene su tarifa superior. Una cuota de solicitudes no es una cuota
de bytes ni de CPU: faltan mediciones de tamaño de respuesta, fallos de caché,
egreso y latencia. Estos planes tampoco limitan el costo fijo del detector,
Redis o los workers: el presupuesto de infraestructura debe vigilarse aparte.

## Margen: escenario, no beneficio garantizado

El informe anterior estima GCP en COP597.592/30 días antes de créditos.
Usando COP4.000/USD como supuesto, no cotización vigente, el piso es
US$149,40/mes. No incluye trabajo, soporte, Workspace, impuestos ni contingencia.
No se usan créditos promocionales para justificar tarifas permanentes.

La referencia anterior de Polar Starter es 5% + US$0,50 por transacción y
1,5% adicional para tarjetas internacionales:
https://polar.sh/resources/pricing . No se ha vuelto a verificar en esta revisión.
Reservamos 9% + US$0,50 por venta para el escenario, sin afirmar que cubra
todos los costos del procesador, conversión, disputas o impuestos.

| Plan | Neto tras reserva de pagos | Costo marginal supuesto a cuota completa | Contribución antes de soporte e impuestos |
| --- | ---: | ---: | ---: |
| Pro | US$16,79 | US$4,00 | US$12,79 |
| Max | US$44,09 | US$12,00 | US$32,09 |
| Ultra | US$116,89 | US$32,00 | US$84,89 |

El costo marginal de US$0,00008/consulta es HIPOTÉTICO; incluye tráfico y
operación incremental sólo para comparar planes. A US$0,00020/consulta,
la contribución bajaría a US$6,79 / US$14,09 / US$36,89 respectivamente.
A US$0,00030, Ultra pierde dinero antes de soporte. Medir antes de activar
ventas o descuentos. En el primer escenario harían falta unos 12 Pro para
cubrir sólo el GCP modelado; no es una promesa de rentabilidad.

Una recarga US$5 deja US$4,05, US$25 deja US$22,25 y US$100 deja US$90,50
antes de servir consultas. US$5 equivaldrían a 10.000 consultas de eventos o
5.000 de estaciones al precio de lista. No vender recargas de US$1 por la
comisión fija. Free no aporta ingresos; su crecimiento también requiere
medición y vigilancia de abuso.

## Activación comercial pendiente

El portal guarda la preferencia del usuario como `selected_plan_id`; esto no
modifica el plan autoritativo ni acredita saldo. `payments_enabled=false` y
`checkout_enabled=false`. La selección se acuerda con Seismik para activación
administrativa. No se ha actualizado el catálogo externo de Polar ni se ha
publicado un checkout en esta revisión.

Antes de aceptar compras faltan webhooks firmados, customer→UID verificado,
entrega idempotente de saldo, renovación/cancelación de las tres suscripciones,
débito de consumo Pay-as-you-go sin sobregiro, reembolsos y conciliación.
El medidor actual cuenta solicitudes autorizadas antes de ejecutar el endpoint,
incluso si éste después falla; definir el tratamiento comercial de errores
antes de cobrar. No hay SLA garantizado ni archivo histórico permanente.
