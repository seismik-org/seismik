# Seismik — avance Sprint Añadido 1

Versión: 0.1  
Fecha de corte: 2026-08-30 (America/Bogota)  
Estado: cierre técnico; API Platform y página pública desplegadas, cierre E2E OAuth pendiente de sincronizar el secreto web en Firebase

## Objetivo

Convertir `devs.seismik.org` en un portal independiente para que identidades
verificadas puedan conocer productos, aceptar términos y administrar claves API
gratuitas con cuotas y trazabilidad.

## Avance por actividad

| ID | Estado | Resultado actual |
|---|---|---|
| SA1-01 | Completo técnico | `seismik.org`, `devs.seismik.org` y `api.seismik.org` sirven funciones separadas por HTTPS; `/developers` es una página informativa independiente |
| SA1-02 | En curso | Google/Firebase habilitado; el nuevo cliente `Seismik for Developers` tiene origen y callbacks autorizados; falta introducir su secreto en Firebase y confirmar identidad |
| SA1-03 | Avanzado | Catálogo moderno y adaptable con productos y subrutas `/v1/...` explícitas |
| SA1-04 | Completo técnico | Alta, listado, rotación y revocación; secreto visible una sola vez y hash en Redis |
| SA1-05 | Completo técnico | Plan Free con límites por minuto/día, máximo de claves y contador de consumo |
| SA1-06 | Completo técnico | Alcances `events:read` y `stations:read`; todas las consultas quedan cerradas por defecto y rechazan ausencia de clave, clave de dispositivo, clave revocada o alcance insuficiente |
| SA1-07 | En curso | Términos beta fechados y aceptación obligatoria; pendiente revisión del Product Owner/legal |
| SA1-08 | En curso | Suite automatizada y despliegue beta aprobados; falta la prueba real identidad → clave temporal → consumo → rotación/revocación |

## Validación de esta iteración

- Backend: 66 pruebas aprobadas.
- Ruff: sin hallazgos.
- mypy: sin hallazgos en 37 archivos fuente.
- JavaScript: sintaxis validada.
- Docker Compose: API y Redis saludables en la VM; Caddy sirve los tres hostnames.
- Portal revisado en producción; el consentimiento Google llega al callback propio.
- Cliente OAuth web nuevo revisado: origen `https://devs.seismik.org` y callback Firebase autorizados.
- Seguridad de datos: historial, recientes y estaciones responden `401` sin `X-Seismik-API-Key`; salud mínima permanece pública.
- OAuth: callback y origen `devs.seismik.org` autorizados; el helper Firebase se sirve bajo el mismo dominio para navegadores con almacenamiento de terceros restringido.

## Próxima puerta de control

1. Introducir en Firebase el secreto del cliente OAuth web nuevo (el valor se muestra enmascarado en Google Cloud y no se registra aquí).
2. Ejecutar el flujo real login → clave temporal → consumo → cuota → rotación/revocación.
3. Confirmar que la clave temporal quedó revocada y no registrar secretos en la evidencia.

No se habilitan cobros ni acceso IoT en este Sprint.
