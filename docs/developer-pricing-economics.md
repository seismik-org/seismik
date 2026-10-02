# Precios de lanzamiento — 1 de octubre de 2026

Precios USD antes de impuestos. Free conserva sus cuotas. Pay-as-you-use:
US$0,0005/eventos y US$0,001/estaciones, con recargas US$5/25/100; Pro:
US$19/mes, 120 solicitudes/min, 20.000/día, 10 claves. Enterprise por contrato.
No se promete disponibilidad garantizada ni archivo histórico permanente.

## Margen: escenario, no beneficio garantizado

El informe de costos estima el ritmo reciente de GCP en COP597.592/30 días,
antes de créditos. Para modelar, NO como cotización vigente, usamos COP4.000/USD:
aproximadamente US$149,40/mes. No cuenta Workspace, trabajo, soporte, impuestos
colombianos ni contingencias. Los créditos de GCP no deben justificar precios
que pierdan dinero una vez expiren.

Polar Starter publica 5% + US$0,50 por transacción y 1,5% extra para tarjetas
internacionales. Hay comisiones de retiro/conversión y disputas. No se contrató
un plan pagado de Polar. Fuente consultada:
https://polar.sh/resources/pricing

Para Pro, reservar conservadoramente 9% + US$0,50 por venta deja US$16,79.
Con un presupuesto HIPOTÉTICO de US$3 por cuenta para tráfico y operación
incremental, la contribución sería US$13,79: aproximadamente 11 cuentas Pro
para cubrir sólo el GCP modelado. Con impuestos sobre el pago, soporte,
devoluciones y otros costos, hace falta más. Usar 15 clientes como objetivo
comercial prudente, no como promesa de rentabilidad.

Una recarga US$5 deja US$4,05 bajo esa misma reserva; US$25 deja US$22,25 y
US$100 deja US$90,50, ANTES de servir las consultas. Por eso no conviene
vender recargas de US$1. El precio de estaciones es mayor que el de eventos.

Falta medir costo marginal real por endpoint y volumen, incluyendo Redis,
egreso y tamaño de respuestas. Revisar semanalmente y antes de dar descuentos
de Enterprise. Free no aporta ingresos y su crecimiento puede elevar el piso
de costos. Ningún análisis sustituye validar derechos de uso de las fuentes.

## Puerta de lanzamiento comercial

Productos privados en Polar: no compartir checkout. El código informa planes,
precios y cuotas, pero conserva payments_enabled=false. Se debe integrar y
probar webhooks firmados, vínculo customer→UID verificado, entrega idempotente
de saldo, cancelación/renovación Pro, límites y cargos, reembolsos y conciliación
antes de aceptar una compra. No usar un producto gratuito como Enterprise:
la negociación no equivale a permitir que el cliente elija cuánto pagar.
