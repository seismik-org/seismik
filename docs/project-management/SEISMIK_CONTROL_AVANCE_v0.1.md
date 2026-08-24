# SEISMIK — CONTROL DE AVANCE DEL MVP

Versión: 0.1  
Fecha de corte: 23 de agosto de 2026  
Estado general: Alfa 0.1 — Sprint 0 en ejecución  
Propietario del control: Codex  
Aprobador: Product Owner

## Control de versiones

| Versión | Fecha | Autor | Cambio | Estado |
|---|---|---|---|---|
| 0.1 | 2026-08-23 | Codex | Registro inicial de control y trazabilidad | Activo |

## 1. Semáforo y estados

| Estado | Código | Significado |
|---|---|---|
| No iniciado | NI | No se ha comenzado y no tiene impedimento activo |
| En curso | EC | Existe trabajo y responsable activo |
| En revisión | ER | Terminado técnicamente, pendiente de evidencia o aceptación |
| Completado | CO | Cumple Definition of Done y fue aceptado cuando aplica |
| Bloqueado | BL | No puede avanzar por dependencia o decisión externa |
| Aplazado | AP | Retirado del Sprint sin eliminarlo del backlog |

Semáforo del Sprint:

- Verde: objetivo alcanzable sin cambios relevantes.
- Amarillo: existe riesgo material, pero hay tratamiento en curso.
- Rojo: el objetivo no puede alcanzarse sin decisión o replanificación.

## 2. Resumen ejecutivo del avance

| Indicador | Valor inicial | Meta MVP | Semáforo | Evidencia |
|---|---:|---:|---|---|
| Progreso de sprints | 0 de 8 aceptados | 8 de 8 | Amarillo | Este documento |
| Análisis Flutter | Sin problemas | Sin problemas | Verde | Ejecución 2026-08-23 |
| Pruebas Flutter | 2 aprobadas | Suite ampliada | Amarillo | `mobile_app/test/` |
| Pruebas backend actuales | No ejecutables por falta de Python activo | Suite completa aprobada | Rojo | Entorno local 2026-08-23 |
| Backend desplegado | No | Sí, ambiente beta | Amarillo | Pendiente Sprint 6 |
| URL móvil real | No, dominio de ejemplo | Sí | Amarillo | `mobile_app/lib/core/constants.dart` |
| Operación en sombra | 0 días | 14 días | Amarillo | Pendiente Sprint 6 |
| Costo cloud activo | 0 COP | ≤150.000 COP/mes | Verde | GCP aún no activado |
| Alertas públicas | 0 | 0 durante MVP | Verde | Política del proyecto |

## 3. Tablero de Sprint 0

| ID | Actividad | Responsable | Estado | Fecha objetivo | Dependencias | Entregable | Evidencia | Aceptación |
|---|---|---|---|---|---|---|---|---|
| S0-01 | Documento maestro y Scrum | Codex | ER | 2026-08-23 | Ninguna | Tres Word y fuentes | `docs/project-management/` | Product Owner |
| S0-02 | Aprobar alcance MVP | Product Owner | NI | Próxima revisión | S0-01 | Decisión registrada | Tabla de decisiones | Product Owner |
| S0-03 | Auditoría de secretos | Codex | EC | 2026-08-23 | Ninguna | Exclusiones seguras | `.gitignore`, `git status` | Codex |
| S0-04 | Primera línea base Git | Codex | NI | 2026-08-23 | S0-03 | Commit inicial | Hash de commit | Codex |
| S0-05 | Backlog y riesgos | Codex | ER | 2026-08-23 | S0-01 | Control de avance | Este documento | Product Owner |
| S0-06 | Aprobar presupuesto beta | Product Owner | NI | Antes de Sprint 3 | S0-02 | Tope mensual | Registro de decisiones | Product Owner |

## 4. Registro maestro de entregables

| Código | Entregable | Sprint | Responsable | Estado | Criterio de aceptación | Ubicación de evidencia |
|---|---|---:|---|---|---|---|
| ENT-001 | Baseline Alfa 0.1 | 0 | Codex | EC | Commit limpio, sin secretos | Git |
| ENT-002 | Gobierno y documentos v0.1 | 0 | Codex + PO | ER | PO revisa alcance y roles | `docs/project-management/` |
| ENT-003 | Detector reproducible | 1 | Codex | NI | Replay y reconexión demostrados | `tests/`, informe Sprint |
| ENT-004 | Detector shadow calibrado | 2 | Codex + asesor | NI | Métricas y revisión científica | Informe de calibración |
| ENT-005 | Backend integrado | 3 | Codex | NI | E2E local aprobado | CI y logs de prueba |
| ENT-006 | Android offline mínimo | 4 | Codex + PO | NI | Prueba en 2+ dispositivos | Evidencia de testing |
| ENT-007 | Simulacro cerrado | 5 | Equipo | NI | Solo testers y marca TEST | Acta y trazas |
| ENT-008 | Entorno beta en sombra | 6 | Codex | NI | 14 días de telemetría iniciados | Dashboard y runbook |
| ENT-009 | MVP Experimental 1.0 | 7 | Equipo | NI | Go/No-Go registrado | Release y acta |

## 5. Registro de puntos de chequeo

| Checkpoint | Momento | Pregunta de control | Evidencia requerida | Decisor |
|---|---|---|---|---|
| CP-00 | Cierre Sprint 0 | ¿Alcance, roles y riesgos son aceptados? | Documentos v0.1 y commit | Product Owner |
| CP-01 | Cierre Sprint 1 | ¿La ingesta es reproducible y recuperable? | Replay, reconexión y tests | Codex |
| CP-02 | Cierre Sprint 2 | ¿Los resultados están medidos sin afirmar certeza? | Matriz y revisión científica | PO + asesor |
| CP-03 | Cierre Sprint 3 | ¿El pipeline local está listo para nube? | E2E, seguridad y ADR | Codex + PO |
| CP-04 | Cierre Sprint 4 | ¿La app funciona con red intermitente? | Pruebas en dispositivos | Product Owner |
| CP-05 | Cierre Sprint 5 | ¿El simulacro es seguro y trazable? | Allowlist, logs y encuesta | Product Owner |
| CP-06 | Semana 1 shadow | ¿Salud y costo están bajo control? | Dashboard y facturación | Codex + PO |
| CP-07 | Cierre Sprint 7 | ¿Se acepta el MVP experimental? | Informe completo | Product Owner |

## 6. Registro de riesgos

| ID | Riesgo | Prob. | Impacto | Nivel | Responsable | Tratamiento | Estado |
|---|---|---|---|---|---|---|---|
| R-01 | Falsa alarma | Alta | Crítico | Crítico | Codex + asesor | Modo sombra y simulacros TEST | Abierto |
| R-02 | No detectar evento | Media | Crítico | Crítico | Codex + asesor | Replay, métricas y redes múltiples | Abierto |
| R-03 | Configuración científica sin asesor | Alta | Alto | Alto | Product Owner | Vincular universidad/sismólogo | Abierto |
| R-04 | Cobertura o caída SeedLink | Alta | Alto | Alto | Codex | Monitoreo, reconexión y redundancia | Abierto |
| R-05 | Costo cloud inesperado | Media | Alto | Alto | PO + Codex | Máximos, cuotas y revisión semanal | Abierto |
| R-06 | Secreto incluido en Git | Baja | Crítico | Alto | Codex | `.gitignore`, scan pre-commit y Secret Manager | En tratamiento |
| R-07 | Falta de Internet durante desastre | Alta | Alto | Alto | Codex | Cola offline MVP; relays posteriores | Abierto |
| R-08 | Restricciones Android/iOS | Media | Alto | Alto | Codex | Prueba real y degradación segura | Abierto |
| R-09 | Abuso de crowdsourcing | Media | Alto | Alto | Codex | App Check, HMAC, rate limit y quorum | Abierto |
| R-10 | Responsabilidad legal/reputacional | Media | Crítico | Crítico | Product Owner | Términos, asesoría y no prometer certificación | Abierto |
| R-11 | Play no autoriza producción | Media | Medio | Medio | Product Owner | Prueba cerrada y cumplimiento temprano | Abierto |
| R-12 | Trabajo concentrado en una persona | Alta | Alto | Alto | Product Owner | Documentación, comunidad y socio académico | Abierto |

## 7. Registro de decisiones

| ID | Fecha | Decisión | Motivo | Responsable | Estado |
|---|---|---|---|---|---|
| DEC-001 | 2026-08-23 | Clasificar versión actual como Alfa 0.1 | No existe despliegue ni validación integral | Product Owner pendiente | Propuesta |
| DEC-002 | 2026-08-23 | MVP limitado a Colombia y Android | Reducir riesgo, costo y tiempo | Product Owner pendiente | Propuesta |
| DEC-003 | 2026-08-23 | Aplazar fotos y videos | Priorizar reporte urgente y controlar almacenamiento | Product Owner indicó | Aceptada |
| DEC-004 | 2026-08-23 | Mantener alertas públicas fuera del MVP | Falta validación científica y operativa | Equipo | Propuesta |
| DEC-005 | 2026-08-23 | No activar GCP hasta que Sprint 3 esté listo | Preservar los 90 días de crédito | Product Owner pendiente | Propuesta |

## 8. Registro de impedimentos

| ID | Detectado | Impedimento | Impacto | Responsable de resolver | Próxima acción | Estado |
|---|---|---|---|---|---|---|
| IMP-001 | 2026-08-23 | Python no está disponible en el entorno activo | No se reejecutan pruebas backend | Codex | Instalar/fijar Python 3.12 en Sprint 1 | Abierto |
| IMP-002 | 2026-08-23 | API móvil apunta a dominio de ejemplo | AAB actual no es publicable | Codex | Crear ambiente beta en Sprint 6 | Abierto |
| IMP-003 | 2026-08-23 | Falta asesor sismológico formal | No se validan umbrales para uso público | Product Owner | Contactar universidad/experto | Abierto |
| IMP-004 | 2026-08-23 | Falta grupo cerrado suficiente | Retrasa elegibilidad Play | Product Owner | Reclutar antes de Sprint 6 | Abierto |

## 9. Evidencia mínima por Sprint

- Hash del commit o tag.
- Resultado de pruebas automatizadas.
- Capturas o logs solo cuando no expongan secretos.
- Métricas de aceptación.
- Defectos conocidos y riesgos actualizados.
- Decisión de Sprint Review.
- Costo real/proyectado desde la activación de nube.
- README y documentos modificados cuando cambie el comportamiento.

## 10. Plantilla de reporte de Sprint

| Campo | Contenido |
|---|---|
| Sprint | Número y fechas |
| Objetivo | Resultado comprometido |
| Resultado | Alcanzado / Parcial / No alcanzado |
| Entregables aceptados | IDs y enlaces |
| Pruebas | Resultado y cobertura relevante |
| Riesgos nuevos/cambiados | IDs |
| Costos | Real, pronóstico y desviación |
| Incidentes | Resumen y acciones |
| Decisiones | IDs y responsable |
| Próximo Sprint | Objetivo propuesto |

## 11. Checklist Go/No-Go del MVP

- [ ] Pipeline replay → candidato → API → bus → push TEST demostrado.
- [ ] Cero secretos en Git y rotación realizada si existió exposición.
- [ ] App Android usa API real de beta y firma válida.
- [ ] Reportes offline sincronizan sin duplicados.
- [ ] Fuentes oficiales muestran atribución y estado.
- [ ] Shadow run de 14 días completado y analizado.
- [ ] Falsos positivos/negativos documentados.
- [ ] Revisión científica adjunta o impedimento aceptado explícitamente.
- [ ] Presupuesto mensual dentro del límite.
- [ ] Privacidad, términos y procedimiento de incidentes revisados.
- [ ] Prueba cerrada de Play completada cuando aplique.
- [ ] Se mantiene prohibición de alertas públicas automáticas.
- [ ] Product Owner registra Go, extensión o No-Go.

## 12. Aprobaciones pendientes

| Aprobación | Responsable | Fecha límite | Estado |
|---|---|---|---|
| Alcance MVP Experimental 1.0 | Product Owner | Cierre Sprint 0 | Pendiente |
| Presupuesto máximo 150.000 COP/mes | Product Owner | Antes de Sprint 3 | Pendiente |
| Activación GCP | Product Owner | Inicio Sprint 6 o antes si E2E lo requiere | Pendiente |
| Ejecución de simulacro con testers | Product Owner | Sprint 5 | Pendiente |
| Carga AAB a Play cerrado | Product Owner | Sprint 7 | Pendiente |
| Decisión Go/No-Go | Product Owner | Cierre Sprint 7 | Pendiente |

