# Auditoría y refuerzo de admin.seismik.org · 8 octubre 2026

Alcance: revisión de código de OAuth, sesión, API administrativa, revisión de reportes,
controles, Worker y HTML/JavaScript; pruebas adversariales locales con datos sintéticos;
escaneo de dependencias backend y comprobaciones públicas de TLS/acceso. No es una
certificación ni un pentest independiente. No se pausaron servicios de producción
ni se intentó acceder a datos de terceros.

## Hallazgos corregidos

| Riesgo | Hallazgo | Corrección |
|---|---|---|
| Alto | La cookie compartida del portal permitía administrar con sólo el primer factor | Admin ignora `seismik_session`. Usa `__Host-Seismik-Admin`, Secure, HttpOnly, SameSite=Strict, Path=/, sin Domain; identificadores guardados como hashes, separados de OAuth |
| Alto | Admin no exigía MFA | Enrolamiento TOTP obligatorio; el secreto candidato expira en cinco minutos y no habilita acceso hasta comprobar un código válido |
| Alto | Pausar/reanudar alertas o publicaciones y revisar reportes sólo exigía sesión | Cada modificación exige un código TOTP nuevo; autorización de un solo uso, vinculada a sesión, acción y parámetros, TTL 120 segundos; verificación en servidor |
| Alto | Cambiar proveedor conservando el correo podía permitir enrolar otro MFA | La primera confirmación vincula de manera atómica el correo autorizado a la identidad estable que configuró MFA; otra identidad no puede reenrolarse. Vincular otro proveedor requiere revisión operativa |
| Medio | Repetición/concurrencia de códigos y recuperación | Contador TOTP monotónico actualizado con WATCH/MULTI; recuperación aleatoria de 128 bits, sólo hashes, cada código de un uso y sólo para entrar; no sirve para aprobar cambios críticos |
| Medio | Fuerza bruta y sesiones abandonadas | Límites por identidad, no sólo por sesión: cinco verificaciones por minuto y veinte por hora; sesiones de ocho horas máximo y quince minutos de inactividad; preautenticación de cinco minutos |
| Medio | Fijación de sesión/CSRF de inicio de sesión | Handoff opaco de 60 segundos, consumo atómico y vinculación a cookie __Host del navegador que inició acceso; rotación tras MFA; estado OAuth consumido con GETDEL |
| Medio | Auditoría y revisión podían divergir | Cambio y auditoría en la misma transacción Redis |
| Medio | JSON malformado o credenciales dentro de texto/JSON anidado podían escapar de la redacción | Ocultar payload no interpretable; redacción acotada por profundidad, JSON anidado, Bearer, JWT y parámetros sensibles; renderizado con textContent |
| Medio | Respuestas tardías podían repoblar datos tras cerrar sesión | Invalidación por generación de solicitudes de resumen, reportes y controles; limpiar códigos, secretos, recuperación y diálogo al cerrar sesión |
| Dependencias | El escaneo inicial de cryptography 46 detectó avisos de seguridad | Backend requiere cryptography >=50,<51; nuevo escaneo del conjunto resuelto sin vulnerabilidades conocidas |

## TLS y borde

Comprobado HTTPS con validación de cadena y hostname para admin, auth e ifeltit:
TLS 1.3, certificado Google Trust Services WE1 válido hasta 27 noviembre 2026.
No se necesita cambiar CA ni comprar certificado para estos hosts. La cabecera
HSTS no prueba por sí sola inclusión en la lista preload del navegador.
Admin mantiene CSP propia sin scripts externos ni inline, frame-ancestors none,
nosniff, no-referrer y no-store. Respuestas observadas antes del cambio: 401 sin
sesión, 403 por API pública y 403 por la URL directa Cloud Run.

## Operación y recuperación

`deploy/provision-admin-mfa.sh` crea una clave Fernet independiente en Secret Manager
sin imprimirla y sólo asigna lectura al service account de la API. Se inyecta con
`SEISMIK_ADMIN_MFA_ENCRYPTION_KEY`; sin clave válida, el inicio MFA falla cerrado.
No reutiliza el secreto del borde. No rotar/destruir esa clave sin migrar previamente
los secretos cifrados; perderla inutiliza los autenticadores registrados.

El usuario completa personalmente el enrolamiento en su aplicación. Añadir cuenta
con clave manual y tipo basado en tiempo; no se usa un generador QR externo.
Los diez códigos de recuperación se muestran una vez después de activar MFA.
Un código ya usado, incluido el de enrolamiento, no puede reutilizarse: esperar al
siguiente código de la aplicación para confirmar otra acción.

Si se pierden autenticador y recuperación, **no hay endpoint de desactivación ni
bypass**. Un operador autorizado debe verificar la identidad fuera del panel,
documentar el incidente, invalidar las sesiones y aprobaciones de esa identidad
y eliminar su registro MFA/vinculación para un nuevo enrolamiento. Guardar respaldo
seguro de Redis y de la clave de cifrado, y probar la recuperación operativa.

## Límites que permanecen

TOTP es compatible con aplicaciones comunes pero puede ser interceptado por phishing
en tiempo real; WebAuthn/passkeys sería un refuerzo posterior. Una sesión robada puede
leer datos hasta expirar, aunque no modificar sin nueva aprobación. La auditoría está
en Redis y no es inmutable frente a un administrador de infraestructura. Esta revisión
no demuestra ausencia de vulnerabilidades ni evalúa completamente IAM, dispositivos
del administrador, extensiones de navegador, WAF o cadenas de suministro de imágenes.

## Verificación reproducible

```bash
python -m pytest
python -m ruff check src tests
python -m mypy src
node --test tests/admin_mfa.test.mjs tests/admin_panel.test.mjs tests/email_auth.test.mjs tests/web_fallback.test.mjs tests/status_history.test.mjs
python -m pip_audit -r requirements-backend.txt --format json
```

Pruebas específicas: vectores RFC 6238; cookies ajenas; acceso pre-MFA; cifrado,
TTL y rotación; replay concurrente; recuperación consumida; límite por identidad;
CSRF entre subdominios; inactividad; revocación; handoff de otro navegador; cambio
de proveedor; redacción; autorización de acción distinta/sesión distinta/repetida.

Referencias: [RFC 6238](https://datatracker.ietf.org/doc/html/rfc6238),
[OWASP MFA](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html),
[OWASP sesiones](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html),
[Fernet](https://cryptography.io/en/latest/fernet/).
