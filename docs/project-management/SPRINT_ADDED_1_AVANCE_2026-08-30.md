# Seismik — avance Sprint Añadido 1

Versión: 0.1  
Fecha de corte: 2026-08-30 (America/Bogota)  
Estado: en curso; API Platform implementada localmente, OAuth y despliegue pendientes

## Objetivo

Convertir `devs.seismik.org` en un portal independiente para que identidades
verificadas puedan conocer productos, aceptar términos y administrar claves API
gratuitas con cuotas y trazabilidad.

## Avance por actividad

| ID | Estado | Resultado actual |
|---|---|---|
| SA1-01 | En curso | Hostnames y Caddy separados en código; falta desplegar y comprobar TLS/origen |
| SA1-02 | En curso | Portal Firebase/OAuth implementado; falta crear/activar la aplicación Web y dominio autorizado |
| SA1-03 | Avanzado | Catálogo moderno, documentación inicial y diseño adaptable listos |
| SA1-04 | Completo técnico | Alta, listado, rotación y revocación; secreto visible una sola vez y hash en Redis |
| SA1-05 | Completo técnico | Plan Free con límites por minuto/día, máximo de claves y contador de consumo |
| SA1-06 | Completo técnico | Alcances `events:read` y `stations:read`; acceso inválido, revocado o insuficiente se rechaza |
| SA1-07 | En curso | Términos beta fechados y aceptación obligatoria; pendiente revisión del Product Owner/legal |
| SA1-08 | En curso | Suite automatizada aprobada; faltan E2E con Firebase real y despliegue beta |

## Validación de esta iteración

- Backend: 65 pruebas aprobadas.
- Ruff: sin hallazgos.
- mypy: sin hallazgos en 37 archivos fuente.
- JavaScript: sintaxis validada.
- Docker Compose: configuración válida; no se ejecutó localmente porque Docker Desktop estaba detenido.
- Portal revisado visualmente en escritorio y móvil.

## Próxima puerta de control

1. Crear o confirmar la aplicación Web Firebase y habilitar Google OAuth.
2. Autorizar `devs.seismik.org` como dominio de autenticación.
3. Configurar los valores públicos Firebase en el entorno beta.
4. Desplegar API/web y ejecutar el flujo real login → clave → consumo → revocación.

No se habilitan cobros ni acceso IoT en este Sprint.
