# Panel de administración: operación centralizada

Pestañas de `admin.seismik.org` y de dónde sale cada dato. Todo lo de clientes es
agregado o pasa por el filtro de privacidad (`docs/ADMIN_BETA_DRILLS.md`).

| Pestaña | Qué muestra | Origen |
|---|---|---|
| Estado | Si X y Facebook publican de verdad (apagada, simulación, publicando, pausada), el modo de push, qué revisión corre cada servicio, la configuración efectiva, la actividad de los registros y la disponibilidad pública de 30 días | Cada servicio publica en Redis, cada 30 s, su revisión (`K_REVISION`) y banderas (nunca secretos): `seismik:operations:info:{alerts,integrations}` |
| Alertas | Alertas enviadas con cuántos dispositivos, sismos oficiales (¿alertó?), detecciones propias, y «¿por qué sonó o no sonó aquí?» | Bitácora de alertas y streams oficial/candidatos; la explicación aplica `AlertPolicy` a un teléfono imaginario |
| Dispositivos | Plataforma, permisos, país, radio y magnitud mínima elegidos, actividad, tokens rechazados por día, y la plataforma de desarrolladores (planes, claves, consultas, webhooks) | Recorrido acotado de `seismik:device:*`; grupos de menos de 5 → `<5` y sin porcentaje |
| Reportes | Lo existente más un mapa de celdas de 0,5° por sismo con intensidad media y esperada | Stream de reportes «¿Lo sentiste?» |
| Registros | Entradas internas, sin datos privados | Streams |
| Auditoría | Quién hizo qué, con las acciones sensibles marcadas | `stream:seismik:developer-audit` |
| Solicitudes | Cola de borrado de cuenta con estado y plazo de 30 días | Stream de solicitudes + `seismik:admin:deletion-status` |
| Seguridad | Sesiones de administración abiertas (cerrar otra con MFA), cuentas de solo lectura, verificaciones MFA | `seismik:admin:session:*` |
| Controles | Pausar o reanudar alertas, X y Facebook | `seismik:operations:paused` |
| Pruebas | Teléfonos de la beta, simulacros (plantillas propias, resultado por plataforma y tiempos) | `seismik:admin:beta-phones`, `seismik:admin:drill-templates` |

## Configuración nueva (API)

- `SEISMIK_ADMIN_READONLY_EMAILS`: correos (separados por coma, y también en
  `SEISMIK_ADMIN_EMAILS`) que ven todo y no pueden cambiar nada: ni aprobar con MFA ni
  guardar plantillas. El panel lo indica en la cabecera.
- `SEISMIK_ADMIN_ALERT_WEBHOOK_URL`: dirección `https://` (Slack, Discord u otra, en
  Secret Manager) a la que se avisa con una línea cuando alguien pausa o reanuda una
  función, inscribe o quita un teléfono, envía un simulacro, cierra una sesión o cambia
  una solicitud de borrado. Nunca incluye datos de clientes. Sin ella no se envía nada.

## Acciones con MFA nuevas

`deletion:<delreq_…>:<estado>` y `session:revoke:<ref>` (además de `beta:*` y `drill:*`).
La lista cerrada vive en `api.admin_security.valid_action`: toda acción nueva del panel
debe añadirse ahí; hay una prueba que lo exige.

## Lo que todavía no está

- **Frescura de cada estación SeedLink.** El detector no publica un latido en Redis. Para
  hacerlo hay que tocar `src/eew`, y eso redespliega el detector por CD (y pisaría un
  despliegue manual, como el de la ML beta). Pendiente de coordinar con Codex.
- **ML en sombra contra el catálogo.** La ML propia no está en `main`.
- **Versión de la app por dispositivo.** El registro del dispositivo no la guarda.
- **Passkeys** y roles más finos que «solo lectura».
- **Correo del solicitante de un borrado.** El panel no lo muestra por diseño; quien tramita
  el borrado usa la herramienta de borrado, no el panel.
- **Aviso de latencia hasta el teléfono** (acuse de la app): hoy se mide cola y envío del servidor.

## Despliegue

API (rutas nuevas), web (pestañas) y `seismik-dispatcher` (latido con información,
métrica de tokens rechazados y detalle del simulacro). No toca el detector. Sin variables
nuevas obligatorias: las dos de arriba son opcionales.
