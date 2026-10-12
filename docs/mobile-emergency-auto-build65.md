# Build 65 — Modo de emergencia automático y rediseñado

El modo de emergencia deja de ser un botón sobre el mapa: **se enciende solo cuando el
teléfono se queda sin señal y se apaga solo cuando la señal vuelve**, en iPhone y en Android.

## Cómo funciona

- **Sin señal:** pasados ~4 s sin ninguna red, el modo se activa. Un corte breve (un túnel, un cambio
  de antena) no lo activa. Una franja roja aparece arriba de toda la app, fuera del mapa
  («Sin señal · Modo de emergencia activo»); tocarla abre la guía.
- **Con señal:** ~1,5 s después de volver la red el modo se apaga, la franja desaparece y se sincroniza
  lo pendiente (registro, historial, reportes en cola, alertas perdidas).
- **Fijarlo:** «Mantener activo aunque haya señal» (al final de la guía) lo deja fijo para señales
  tan débiles que nada carga. Sólo la persona lo apaga. «Buscar señal y sincronizar» apaga lo fijado si
  el sistema ve red; si no, lo dice con claridad.
- El modo ya **no se hereda** de la última vez: arranca sólo si la persona lo fijó.
- iPhone usa `NWPathMonitor`; Android usa `connectivity_plus`. «Hay red» significa que el sistema
  ve una interfaz con conexión: no detecta un Wi-Fi con portal cautivo o sin salida a internet; para eso
  está la opción de fijarlo.

## La pantalla

Tarjetas en lugar de una lista de textos: estado (con el botón de buscar señal), «Si está temblando»
(Agáchate · Cúbrete · Sujétate), «Cuando pare», punto de encuentro y notas (sólo en el teléfono),
reportes pendientes, últimos sismos guardados y opciones. Mantiene la guía de los CDC, el aviso de
independencia y que nada de lo guardado confirma que alguien esté a salvo.

## No cambia

- No se corta Internet ni se desactivan las alertas push, los sensores autorizados o el registro seguro.
- Los reportes sin señal quedan en cola con su `report_id`, como en el build 64.
