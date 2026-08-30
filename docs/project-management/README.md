# Gestión del proyecto Seismik

## Evidencia de sprints

- [Cierre técnico Sprint 1 — 2026-08-24](SPRINT_1_CIERRE_2026-08-24.md)
- [Cierre técnico Sprint 2 — 2026-08-24](SPRINT_2_CIERRE_TECNICO_2026-08-24.md)
- [Avance técnico Sprint 3 — 2026-08-26](SPRINT_3_AVANCE_2026-08-26.md)
- [Cierre técnico Sprint 3 — 2026-08-27](SPRINT_3_CIERRE_TECNICO_2026-08-27.md)
- [Avance técnico Sprint 4 — 2026-08-27](SPRINT_4_AVANCE_2026-08-27.md)
- [Avance Sprint Añadido 1 — 2026-08-30](SPRINT_ADDED_1_AVANCE_2026-08-30.md)

Este directorio es la fuente verificable compartida para el gobierno y seguimiento
del proyecto. Los archivos Markdown permiten revisar cambios línea por línea en Git;
las copias `.docx` son los documentos formales para reuniones y aprobación.

## Documentos vigentes

| Documento | Fuente editable | Copia Word | Versión | Estado |
|---|---|---|---|---|
| Documento maestro | `SEISMIK_DOCUMENTO_MAESTRO_v0.1.md` | `SEISMIK_DOCUMENTO_MAESTRO_v0.1.docx` | 0.1 | Borrador para aprobación |
| Plan Scrum del MVP | `SEISMIK_PLAN_SCRUM_MVP_v0.2.md` | `SEISMIK_PLAN_SCRUM_MVP_v0.2.docx` | 0.2 | En ejecución; Sprint Añadido 1 en curso |
| Control de avance | `SEISMIK_CONTROL_AVANCE_v0.1.md` | `SEISMIK_CONTROL_AVANCE_v0.1.docx` | 0.1 | Activo |
| Paquete de revisión sismológica | `PAQUETE_REVISION_SISMOLOGICA_v0.1.md` | `PAQUETE_REVISION_SISMOLOGICA_v0.1.docx` | 0.1 | Pendiente de revisor |

## Convención de versiones

- `0.x`: planificación y prototipos anteriores al MVP aceptado.
- `1.0`: MVP experimental aceptado mediante decisión Go/No-Go.
- Incremento menor (`0.1` a `0.2`): cambios de alcance, planificación o criterios.
- Corrección (`0.1.0` a `0.1.1`): correcciones editoriales sin cambiar alcance.
- Ningún documento aprobado se sobrescribe: se crea una nueva versión.

## Responsables

- Propietario del producto y aprobador: usuario/promotor de Seismik.
- Arquitectura, implementación y documentación técnica: Codex.
- Aceptación: Product Owner, con evidencia técnica preparada por Codex.

## Actualización

1. Modificar primero la fuente Markdown.
2. Actualizar la tabla de control de versiones del documento.
3. Regenerar Word con `tools/generate_project_docs.ps1`.
4. Ejecutar validaciones y revisar que no existan secretos.
5. Registrar el cambio en Git.
