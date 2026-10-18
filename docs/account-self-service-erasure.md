# Eliminación de cuenta por su dueño

`/delete-account/` ofrece dos caminos. Quien puede iniciar sesión borra su cuenta al instante;
quien no, usa el formulario por correo de siempre (una persona verifica y borra).

## Flujo
1. `GET /v1/account/erasure/login` pone la marca fija `seismik_after_login=delete-account` y lleva a
   `auth.seismik.org/id`. Al volver, `_finish_login` redirige a una URL constante
   (`account_erasure_return_url`); un valor distinto de la marca se ignora, igual que con Waves.
2. `GET /v1/account/erasure` (cookie de sesión) devuelve el correo enmascarado, si el inicio de sesión
   es reciente y cuántos dispositivos, claves y círculos hay.
3. `POST /v1/account/erasure` con `{"confirm": "ELIMINAR"}`. Exige: cookie de sesión válida, inicio de
   sesión de los últimos 10 minutos (si no, `401 reauth_required`), cabecera `Origin: https://seismik.org`
   y un máximo de 5 intentos por hora y cuenta.

## Qué borra (`src/api/account_erasure.py`)
Dispositivos (registro, token, índices, sesiones), pertenencia a círculos familiares (ubicaciones,
estados, alias; el círculo pasa a quien entró primero y se cierra si queda vacío), claves de API con
su uso, perfil de desarrollador y webhooks, reportes enviados desde sus dispositivos (se quitan de las
colas de reportes de sentido y de daños), el vínculo de identidad de Firebase y el usuario de Firebase
Authentication. Todo paso es idempotente.

## Qué conserva
El libro contable de facturación, si existe (obligación legal). Una entrada en la cola de eliminaciones
del panel de administración, sin correo, con el estado `completed` y el origen `self_service`.

## Sesiones
Se guarda `seismik:account:erased:{uid}` con la hora. `validate_session` rechaza toda sesión
(web o móvil) iniciada antes de ese segundo; un inicio de sesión posterior crea una cuenta nueva y vacía.

## Despliegue
Cambia `src/api/**`: al fusionar en `main` el CD vuelve a desplegar API, dispatcher e integraciones.
Antes hay que reconciliar con el árbol de producción manual (ver
`docs/associated-earthquake-reports.md`). Al desplegar, actualizar §9 de la política de privacidad
(«una persona de nuestro equipo revisa cada solicitud») para mencionar la eliminación inmediata.

## Correo saliente (Resend)
`src/api/mailer.py` envía por Resend desde dos remitentes del dominio verificado `seismik.org`:
`Seismik <cuentas@seismik.org>` (cuentas y datos personales; las respuestas van a `support@seismik.org`) y
`Seismik <noreply@seismik.org>` (avisos automáticos sin respuesta; hoy sin uso). Resend no registra
direcciones: sirve cualquier nombre del dominio verificado. Sin `SEISMIK_RESEND_API_KEY` no se envía nada.
Correos actuales, todos en español (`mail_templates.py`): confirmación al terminar una eliminación con
sesión, y acuse de recibo del formulario (uno por correo y día). Ningún correo se guarda.
Activar: crear en Resend una clave `seismik-api` con permiso de envío limitado a seismik.org, guardarla en
Secret Manager (`seismik-resend-api-key`) y montarla en Cloud Run como `SEISMIK_RESEND_API_KEY`.
Al activarlo, la política de privacidad debe nombrar a Resend (envíos desde São Paulo).
