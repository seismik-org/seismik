# Acceso con correo de Seismik

Se reutiliza `seismik-15bbb`. Firebase Authentication mantiene contraseñas y
envía correos; no se instala Firestore, teléfono ni otra base de cuentas.
Apple, Google y GitHub siguen usando el OAuth de FastAPI.

## Configuración

Variables públicas: `SEISMIK_EMAIL_LOGIN_ENABLED=true`,
`SEISMIK_FIREBASE_WEB_API_KEY`, `SEISMIK_FIREBASE_WEB_PROJECT_ID=seismik-15bbb`,
`SEISMIK_FIREBASE_WEB_AUTH_DOMAIN=seismik-15bbb.firebaseapp.com` y
`SEISMIK_FIREBASE_WEB_APP_ID`. La configuración web se entrega desde
`/v1/oauth/email/config`; la clave web de Firebase no es una credencial Admin.
Reutilizar `SEISMIK_FIREBASE_CREDENTIALS_PATH` y su montaje actual, sin copiar
el JSON al repositorio. La cuenta de servicio necesita consultar usuarios de
Firebase Auth para comprobar revocación (`firebaseauth.users.get`).

En Authentication → Método de acceso, habilitar Correo/contraseña y mantener
deshabilitado el acceso sin contraseña. En Configuración, conservar los
dominios existentes y añadir `auth.seismik.org`; conservar `devs.seismik.org`.
Elegir «Crear varias cuentas para cada proveedor de identidad» para impedir
que Firebase vincule por correo. La vinculación de Seismik se hace por pruebas
de identidad, no por direcciones de correo. Activar
`emailPrivacyConfig.enableImprovedEmailPrivacy` mediante la API administrativa.
Usar las cuotas de Firebase y la política de contraseña (mínimo 12 caracteres).

En Plantillas, idioma español, remitente Seismik, asunto «Verifica tu correo
para Seismik» y «Recupera tu contraseña de Seismik». Firebase fija el cuerpo de
verificación; su traducción incluye `%APP_NAME%`. La marca del proyecto debe
ser Seismik. El cuerpo de recuperación puede personalizarse, conservando
`%LINK%`. Después de desplegar y comprobar la página, establecer la URL de
acción compartida en `https://auth.seismik.org/auth.html`. Se manejan
`verifyEmail`, `resetPassword`, `recoverEmail` y `verifyAndChangeEmail`.
Nunca abrir ni guardar códigos de usuarios reales en documentación o logs.

Los correos usan `languageCode=es` y continuación fija
`https://auth.seismik.org/id`. El cliente ignora `continueUrl` ajenos.
No se cambia el `authDomain` de Firebase a auth.seismik.org: los proveedores
propios siguen utilizando sus callbacks actuales en ese dominio.

## Sesiones y conservación de datos

El navegador utiliza persistencia Firebase sólo en memoria. Tras comprobar
el correo, envía un ID token a `/v1/oauth/email/exchange` desde el origen
`https://auth.seismik.org`. El backend verifica firma, audiencia, emisor,
vigencia, revocación, correo verificado, proveedor password y autenticación
reciente (5 minutos). Firebase Admin comprueba audiencia/emisor del proyecto
de la credencial existente. El backend no recibe contraseñas.

Se emite la cookie actual `seismik_session`, Secure/HttpOnly/SameSite=Lax,
para `.seismik.org`. Se rota y elimina la cookie anterior. La app inicia
`/v1/oauth/authorize?provider=email&origin=app&app_challenge=...`; recibe el
código habitual en `seismik://auth/callback` y lo canjea con su verificador
PKCE. Los códigos duran 60 segundos y las intenciones 10 minutos. No se
admiten retornos arbitrarios. Las sesiones móviles y de dispositivo se
mantienen en sus espacios actuales. Logout móvil revoca el token en Redis;
sin conexión elimina el acceso local y el servidor conserva el TTL.

Las sesiones de correo guardan UID de Firebase y auth_time, no ID tokens.
En cada uso protegido se consultan estado, verificación y fecha de revocación
de Firebase. Recuperar contraseña, deshabilitar el usuario o quitar la
verificación invalida estas sesiones. Las sesiones OAuth anteriores siguen
funcionando. Esta consulta añade una llamada Firebase por petición protegida;
si Firebase falla, el acceso con correo falla cerrado.

La relación persistente `seismik:identity:firebase:<sha256(uid)>` apunta al UID
original de Seismik. La primera asignación utiliza SET NX y no se sobrescribe.
Nunca expira: se incluye en los backups existentes de Redis.

**Para un usuario existente:** entrar con Apple, Google o GitHub; regresar a
`auth.seismik.org/id` en cinco minutos; crear/verificar el acceso con correo;
volver a autenticar ambas identidades si pasó el plazo; marcar «Vincular a mi
cuenta actual de Seismik» e iniciar sesión con contraseña. La casilla es una
decisión explícita y el servidor requiere ambas pruebas. También se puede
completar en el navegador de la app, que comparte la cookie del acceso OAuth.

Vincular antes del primer canje del correo. Si la identidad de Firebase ya se
usó en Seismik o tiene datos, se rechaza el cambio (409), conservando ambas
cuentas. No hay una migración o fusión automática de cuentas ya pobladas.
Familias, dispositivos, planes, claves API y webhooks permanecen bajo el UID
existente. Los Bearer Firebase del portal resuelven la misma relación.

## Abuso

El canje permite 20 intentos/minuto por IP observada por FastAPI, usando un
hash y ventana Redis con caducidad. Detrás del proxy este límite puede
agrupar conexiones; ajustar infraestructura antes de elevarlo. Se exige
Origin y JSON para impedir CSRF. Registro y recuperación no consultan si el
correo existe y muestran mensajes neutros. Firebase controla los intentos
directos de contraseña y envío de correo; activar su protección contra
enumeración es parte obligatoria de la configuración, no sustituible por UI.

## Publicación y verificación

CI prueba backend, lint/tipos, Flutter y compilaciones Android/iOS. En main
actualiza Cloud Run sin reemplazar las otras variables ni los secretos, y
activa `SEISMIK_EMAIL_LOGIN_ENABLED`. El Worker `seismik` está conectado a
GitHub en Cloudflare (comprobado el 2026-10-06), aunque la documentación
anterior decía que su publicación era manual. Conservar sincronizados
`edge-worker/worker.js` y `deploy/cloudflare-edge-router.js`. Su CSP permite
gstatic y los endpoints de Firebase también en auth.seismik.org.

Pruebas locales: `pytest`, `ruff check src tests`, `mypy src`,
`node --test tests/web_fallback.test.mjs`. `tests/test_firebase_login.py`
comprueba tokens inválidos/no verificados, CSRF, límites, sesiones y logout,
PKCE/códigos de un uso, revocación y vinculación conservando datos.
Los proveedores Firebase están simulados: esto no prueba entrega de correo.
Verificar con un buzón controlado registro → verificación → login → logout,
recuperación → nueva contraseña → rechazo de sesión anterior, y vinculación
con una cuenta de prueba. Comprobar también los tres proveedores en vivo.

Reversión: desactivar `SEISMIK_EMAIL_LOGIN_ENABLED` y volver a las revisiones
anteriores de API/web/Worker. No borrar usuarios Firebase, relaciones Redis,
familias o claves API al revertir.
