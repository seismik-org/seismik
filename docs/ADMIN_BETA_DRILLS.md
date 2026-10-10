# Privacidad del panel, teléfonos de prueba y simulacros

## El panel ya no muestra datos privados de clientes

La privacidad se aplica en la API (`src/api/admin_privacy.py`), no en la página:
el navegador del administrador nunca recibe el dato. Vale para **Registros**
(`/v1/admin/records/{nombre}`) y para **Reportes** (`/v1/reports/admin/reports`).

| Dato | Qué se ve |
|---|---|
| Nombres (también los de Familia: `display_name`, `name`…) | `•••` |
| Correos, teléfonos, direcciones, contactos, endpoints de clientes | `•••` (los correos de los administradores sí salen en su propia auditoría) |
| Mensajes y comentarios libres (`message`, `comment`, `details`, `body`…) | `•••` |
| Identificadores de dispositivo, cuenta, círculo, miembro, webhook, clave… | `id:` + 10 caracteres de un HMAC con la clave del panel: sirve para ver que dos entradas son de la misma cuenta, no para saber de quién ni revertirlo |
| Latitud y longitud de clientes (reportes, familia, borrados…) | redondeadas a 0,1° (~11 km) |
| Sismos oficiales, detecciones, alertas y publicaciones | sin cambios (son datos públicos); sólo se filtran correos |

Las pruebas de notificaciones (`push_audit`) conservan el título y el texto de
sismos públicos, pero un aviso de Familia pierde el nombre aunque venga dentro
del título. No hay interruptor para quitar esta protección. Nota: el código
cambia si se rota `SEISMIK_ADMIN_MFA_ENCRYPTION_KEY`.

El **Resumen** sólo cuenta cosas (cuentas, dispositivos, círculos); no muestra a nadie.

## Teléfonos de prueba (beta)

Pestaña **Pruebas**. Inscribir un teléfono necesita su *identificador del
dispositivo* (Ajustes de la app → «Identificador de este dispositivo» → copiar;
no es un dato personal) y que ese teléfono ya se haya registrado con la app
abierta. El panel guarda el nombre que le des y sólo muestra los últimos cuatro
caracteres del identificador.

- `GET /v1/admin/beta-phones`: lista (nombre, plataforma, si tiene token de
  notificaciones, si permite alertas críticas) y los escenarios.
- `POST /v1/admin/beta-phones` `{device_id, label}`: inscribe (hasta 50).
- `DELETE /v1/admin/beta-phones/{ref}`: lo quita. `ref` es un código de 16
  caracteres, no el identificador.

Inscribir y quitar piden un código MFA nuevo ligado a ese teléfono
(`beta:add:<ref>`, `beta:remove:<ref>`), se limitan a 30 por hora y quedan en la
auditoría (`beta_phone.enrolled` / `beta_phone.removed`). Redis:
`seismik:admin:beta-phones`.

## Simulacros dirigidos

`POST /v1/admin/drills` `{scenario: bogota|pacifico|atacama, critical, refs[1..10]}`.

- **Sólo a teléfonos inscritos y seleccionados.** La API comprueba que estén
  inscritos y con token; el dispatcher lo vuelve a comprobar al enviar, así que
  quitar un teléfono antes de que salga lo excluye.
- **El MFA aprueba esa acción exacta:** escenario, alarma o aviso y esos
  teléfonos (`drill:<escenario>:<critical|notice>:<huella>`). Se limita a 6 por hora.
- **Marcado como simulacro:** `event_id` = `drill-…` (la marca que ya reconocen
  las apps: no entra en el historial de sismos, ni en la memoria de alarmas, ni
  se ofrece para reportar), fuente `simulation`, título «SIMULACRO: …» y lugar
  «Simulacro — …».
- **No toca nada real:** va por su propio stream (`stream:seismik:admin-drills`)
  y el dispatcher lo envía directo (`_handle_admin_drill`): no pasa por la política
  de alertas, ni por integraciones, webhooks, X, Facebook, bitácora de alertas ni
  ubicación familiar. No depende de la pausa de alertas (no es un sismo) y lo
  respeta `push_mode` (en `dry_run` queda registrado y no sale; en `testers` sólo
  llega a quien esté también en `SEISMIK_PUSH_TEST_DEVICE_IDS`).
- **Alarma crítica:** en Android llega como el mensaje de datos de prioridad alta
  que dispara la alarma a pantalla completa; en iPhone usa sonido crítico si el
  teléfono tiene el permiso autorizado, si no, «time-sensitive».
- Una reentrega del stream no repite el simulacro (`seismik:admin:drill:push:<id>`).
  El resultado (`sent`, `dry_run`, `no_targets`, intentos y éxitos) se guarda 7
  días en `seismik:admin:drill:<id>` y aparece en «Últimos simulacros».

## Despliegue

Requiere desplegar **API** (rutas y privacidad), **web** (pestaña Pruebas) y
**seismik-dispatcher** (consume `admin_drill`). No hay variables ni secretos
nuevos. Hasta que el dispatcher se despliegue, un simulacro queda «En cola».
Probar primero con `push_mode=dry_run` o con un solo teléfono propio.
