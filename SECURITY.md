# Seguridad

No abras un issue público para vulnerabilidades. Envía un reporte privado al
correo de seguridad que el despliegue público configure en GitHub Security
Advisories, incluyendo versión, impacto, reproducción mínima y mitigación sugerida.

No incluyas tokens, ubicaciones reales, credenciales ni datos de dispositivos.
Los mantenedores acusarán recibo, clasificarán severidad y coordinarán una
publicación responsable. Hasta configurar un contacto operativo, no se debe
presentar este repositorio como servicio público activo.

Alcance prioritario: falsificación/replay de alertas, bypass de App Check,
exposición de ubicación, envenenamiento del quorum H3, abuso de push, SSRF y
agotamiento de Redis. La investigación nunca autoriza probar sobre usuarios,
estaciones o agencias de terceros sin permiso.

## Repositorio público y credenciales

El código puede ser público sin publicar la identidad ni los datos de producción.
No añadas archivos de firma, claves privadas, cuentas de servicio, contraseñas,
sesiones, exportaciones de bases de datos ni información de usuarios. Usa ejemplos
con dominios reservados y valores ficticios. Los archivos Firebase locales y las
claves de Maps se mantienen fuera de Git; una app instalada puede revelar sus
claves cliente y necesita restricciones y autorización del servidor igualmente.

GitHub Secret Scanning y Push Protection deben permanecer activos. El flujo
`public-security` ejecuta Gitleaks sobre el historial completo con salida censurada.
Sus excepciones son huellas exactas de ejemplos o identificadores públicos
revisados: no se excluyen archivos enteros ni se aceptan comentarios que omitan
el escaneo. Antes de confirmar cambios, revisa también los archivos preparados
con `gitleaks git --staged --redact=100` y las pruebas de secretos de `tests/`.

No publiques informes de escaneo que contengan valores de credenciales. Si una
credencial real llega a Git, retirar su línea no la revoca: prepara una rotación
compatible, comprueba sus consumidores y trata la exposición histórica. Conserva
los respaldos únicamente en almacenamiento privado y evita sobrescribir ramas o
datos durante la limpieza.
