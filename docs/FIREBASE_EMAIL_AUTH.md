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
Si hay otra cuenta abierta y el correo todavía no tiene una relación, se
requiere elegir explícitamente la vinculación o cerrar esa sesión antes de
crear un acceso separado. Así no se sustituye inadvertidamente la cuenta
existente por una cuenta vacía.

## Abuso

El canje permite 20 intentos/minuto por IP, usando un hash y ventana Redis
con caducidad. Con la guardia de origen activa se utiliza CF-Connecting-IP
del Worker autenticado; sin ella se utiliza la conexión observada por FastAPI.
Se exige
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
`node --test tests/web_fallback.test.mjs tests/email_auth.test.mjs`. `tests/test_firebase_login.py`
comprueba tokens inválidos/no verificados, CSRF, límites, sesiones y logout,
PKCE/códigos de un uso, revocación y vinculación conservando datos.
Los proveedores Firebase están simulados: esto no prueba entrega de correo.
Las pruebas JS cubren registro, verificación, recuperación, mensajes neutros,
limpieza de contraseña y canje que sólo contiene el ID token.
La pantalla separa «Iniciar sesión» y «Crear cuenta» en vistas explícitas.
Crear cuenta solicita confirmación de contraseña y envía el registro desde
el botón principal o Enter; esa vista nunca ejecuta el login. Recuperación
tiene una vista que sólo requiere correo. Los errores de creación y de envío
de verificación se muestran por separado; no se anuncia un registro completado
si Firebase rechazó su creación.
Verificar con un buzón controlado registro → verificación → login → logout,
recuperación → nueva contraseña → rechazo de sesión anterior, y vinculación
con una cuenta de prueba. Comprobar también los tres proveedores en vivo.

Reversión: desactivar `SEISMIK_EMAIL_LOGIN_ENABLED` y volver a las revisiones
anteriores de API/web/Worker. No borrar usuarios Firebase, relaciones Redis,
familias o claves API al revertir.

## Configuración comprobada el 2026-10-06

En el proyecto existente se habilitó Email/Password (sin acceso por enlace ni
teléfono), se añadió auth.seismik.org, se desactivó la combinación automática
por correo, se guardó idioma español y se exigió mínimo 12 caracteres sin
forzar actualización en accesos actuales.
`emailPrivacyConfig.enableImprovedEmailPrivacy=true` se confirmó mediante la
API administrativa (HTTP 200). Cloud Shell necesitó la cabecera
`x-goog-user-project: seismik-15bbb` para usar la cuota del proyecto; el token
administrativo no se imprimió ni se guardó en archivos. La credencial montada
pertenece a este proyecto y ya tiene `roles/firebaseauth.admin`; no se crearon
claves ni permisos nuevos.

La implementación se fusionó en la PR #2 (commit desplegado
`fc02b214e3b162eb21480c986c1601438f3b7fb9`). El
[run de Actions](https://github.com/seismik-org/seismik/actions/runs/37500192391)
terminó con éxito en backend, JavaScript, Flutter, Android, iOS y pruebas
nativas, y desplegó API, web y los workers afectados. Cloudflare publicó esa
versión con el 100 % del tráfico.

En producción se comprobó `/id`, los assets y la configuración de correo
(HTTP 200 y flag activo), CSP de Firebase, rechazo de token inválido (401),
otro Origin (403), sesión ausente (401), logout (204), requisito PKCE (400)
y redirección móvil al formulario de correo. Apple, Google y GitHub siguen
habilitados y sus inicios redirigen a los dominios correctos; no se completó
el callback de cada proveedor con una cuenta real. Firebase devuelve
`INVALID_LOGIN_CREDENTIALS` para una identidad sintética y HTTP 200 neutro
en recuperación. El navegador mostró el error de un enlace sintético inválido.

**Pendiente por restricción de Firebase:** la consola y la API administrativa
rechazan cambios de remitente, asunto, cuerpo y URL de acción con HTTP 400
`EMAIL_TEMPLATE_UPDATE_NOT_ALLOWED`. La consola indica que el proyecto no
puede actualizar plantillas y remite a
[soporte de Firebase](https://firebase.google.com/support/troubleshooter/auth/email/help).
Los cambios de marca personalizados intentados no quedaron guardados.
El idioma español sí quedó guardado; continúan las plantillas predeterminadas
y el enlace funcional `https://seismik-15bbb.firebaseapp.com/__/auth/action`,
con continuación fija a `https://auth.seismik.org/id`. El handler personalizado
en auth.seismik.org está desplegado, pero no es aún el destino de los correos.
Cuando soporte habilite la edición, aplicar remitente/asuntos/cuerpo indicados
arriba y URL compartida `https://auth.seismik.org/auth.html`, y comprobar que
persisten después de recargar la consola.

Falta un buzón controlado para comprobar entrega y completar en producción
registro, verificación, login, recuperación y vinculación con datos reales.
Esos flujos pasaron pruebas automatizadas con Firebase simulado. Los cambios
móviles compilaron; la distribución de nuevos binarios por las tiendas queda
fuera del despliegue de Cloud Run y pendiente.
