# SEISMIK — CONTROL DE AVANCE DEL MVP

Versión: 0.1.3
Fecha de corte: 26 de agosto de 2026
Estado general: Alfa 0.1 — Sprint 3 en curso; E2E Docker pendiente de WSL 2
Propietario del control: Codex  
Aprobador: Product Owner

## Control de versiones

| Versión | Fecha | Autor | Cambio | Estado |
|---|---|---|---|---|
| 0.1 | 2026-08-23 | Codex | Registro inicial de control y trazabilidad | Activo |
| 0.1.1 | 2026-08-24 | Codex | Evidencia y cierre técnico del Sprint 1 | Activo |
| 0.1.2 | 2026-08-24 | Codex | Calibración sombra y cierre técnico del Sprint 2 | Activo |
| 0.1.3 | 2026-08-26 | Codex | Seguridad, bus y avance técnico del Sprint 3 | Activo |

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
| Progreso de sprints | 2 de 8 cerrados técnicamente | 8 de 8 | Amarillo | Informes Sprint 1 y 2 |
| Análisis Flutter | Sin problemas | Sin problemas | Verde | Ejecución 2026-08-23 |
| Pruebas Flutter | 2 aprobadas | Suite ampliada | Amarillo | `mobile_app/test/` |
| Pruebas backend actuales | 55 aprobadas; Ruff y mypy limpios | Suite completa aprobada | Verde | Entorno local 2026-08-26 |
| Backend desplegado | No | Sí, ambiente beta | Amarillo | Pendiente Sprint 6 |
| URL móvil real | No, dominio de ejemplo | Sí | Amarillo | `mobile_app/lib/core/constants.dart` |
| Operación en sombra | 0 días | 14 días | Amarillo | Pendiente Sprint 6 |
| Costo cloud activo | 0 COP | ≤150.000 COP/mes | Verde | GCP aún no activado |
| Alertas públicas | 0 | 0 durante MVP | Verde | Política del proyecto |

## 3. Tablero de Sprint 0

| ID | Actividad | Responsable | Estado | Fecha objetivo | Dependencias | Entregable | Evidencia | Aceptación |
|---|---|---|---|---|---|---|---|---|
| S0-01 | Documento maestro y Scrum | Codex | CO | 2026-08-23 | Ninguna | Tres Word y fuentes | `docs/project-management/` | Creación completada; revisión PO pendiente en S0-02 |
| S0-02 | Aprobar alcance MVP | Product Owner | NI | Próxima revisión | S0-01 | Decisión registrada | Tabla de decisiones | Product Owner |
| S0-03 | Auditoría de secretos | Codex | CO | 2026-08-23 | Ninguna | Exclusiones seguras | `.gitignore`; scan sin hallazgos | Codex |
| S0-04 | Primera línea base Git | Codex | CO | 2026-08-23 | S0-03 | Commit inicial | `d8382c10dfa219551da3d696943be478c55d8b7b` | Codex |
| S0-05 | Backlog y riesgos | Codex | CO | 2026-08-23 | S0-01 | Control de avance | Este documento | Creación completada; PO revisa en S0-02 |
| S0-06 | Aprobar presupuesto beta | Product Owner | NI | Antes de Sprint 3 | S0-02 | Tope mensual | Registro de decisiones | Product Owner |

## 3.1 Tablero de Sprint 1

| ID | Actividad | Responsable | Estado | Entregable | Evidencia |
|---|---|---|---|---|---|
| S1-01 | Fijar Python y calidad | Codex | CO | Python 3.12.10 + herramientas | `.python-version`, `pyproject.toml` |
| S1-02 | Verificar estaciones CM | Codex | CO | Catálogo fechado | `data/stations/` |
| S1-03 | Reconexión y gaps | Codex | CO | Cliente recuperable y contadores | `src/eew/`, tests |
| S1-04 | Replay MiniSEED | Codex | CO | Runner determinista | `src/eew/replay.py` |
| S1-05 | Casos históricos y ruido | Codex + asesor | ER | 4 fixtures con hashes | `data/replay/manifest.json`; revisión científica pendiente |
| S1-06 | Suite backend | Codex | CO | 32 pruebas aprobadas | pytest/Ruff/mypy 2026-08-24 |

## 3.2 Tablero de Sprint 2

| ID | Actividad | Responsable | Estado | Entregable | Evidencia |
|---|---|---|---|---|---|
| S2-01 | Parametrizar DSP/STA-LTA | Codex | CO | Perfil `CM.HHZ` | `config.json`, `src/eew/config.py` |
| S2-02 | Validar coincidencia y geometría | Codex | CO | Quorum, apertura y lag | `src/eew/coincidence.py`, tests |
| S2-03 | Medir replay | Codex | CO técnico | Matrices de 36 + 18 perfiles | `data/calibration/` |
| S2-04 | Correlación SGC | Codex + asesor | ER | Matcher y contrato SGC | `test_official.py`, `sgc-association.json` |
| S2-05 | Salud y lag por estación | Codex | CO | Snapshot observable | `src/eew/seedlink.py`, tests |
| S2-06 | Revisión sismológica | PO + asesor | BL | Acta independiente | Paquete listo; falta revisor |

## 3.3 Tablero de Sprint 3

| ID | Actividad | Responsable | Estado | Entregable | Evidencia |
|---|---|---|---|---|---|
| S3-01 | Contratos Pydantic/OpenAPI | Codex | CO | OpenAPI v1 estricta | `docs/api/openapi-v1.json`, tests |
| S3-02 | HMAC, replay e idempotencia | Codex | CO | Ingesta endurecida | 413/401/422, duplicados y bus atómico probados |
| S3-03 | Elegir bus MVP | Codex propone; PO aprueba | CO técnico | ADR Redis Streams | `ADR-0001-redis-streams-mvp.md` |
| S3-04 | App Check y registro | Codex | CO técnico | Integridad tipada | Token inválido y configuración productiva probados |
| S3-05 | Dispatcher seguro | Codex | CO | Dry run auditable y allowlist | `stream:seismik:push-test`, tests |
| S3-06 | E2E local | Codex | ER | Replay → payload TEST | E2E en memoria aprobado; Compose pendiente |
| S3-07 | IaC, cuotas y límites | Codex | CO técnico | Guardrails sin recursos | `deploy/README.md`, `.env.example` |

## 4. Registro maestro de entregables

| Código | Entregable | Sprint | Responsable | Estado | Criterio de aceptación | Ubicación de evidencia |
|---|---|---:|---|---|---|---|
| ENT-001 | Baseline Alfa 0.1 | 0 | Codex | CO | Commit limpio, sin secretos | `d8382c10dfa219551da3d696943be478c55d8b7b` |
| ENT-002 | Gobierno y documentos v0.1 | 0 | Codex + PO | ER | PO revisa alcance y roles | `docs/project-management/` |
| ENT-003 | Detector reproducible | 1 | Codex | CO | Replay y reconexión demostrados | `SPRINT_1_CIERRE_2026-08-24.md` |
| ENT-004 | Detector shadow calibrado | 2 | Codex + asesor | ER | Métricas listas; revisión científica pendiente | `SPRINT_2_CIERRE_TECNICO_2026-08-24.md` |
| ENT-005 | Backend integrado | 3 | Codex | ER | E2E en memoria aprobado; falta Compose real | Tests y `SPRINT_3_AVANCE_2026-08-26.md` |
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
| R-01 | Falsa alarma | Alta | Crítico | Crítico | Codex + asesor | Modo sombra; calibrar tras 2 candidatos en ruido | En tratamiento |
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
| DEC-006 | 2026-08-24 | Mantener No-Go público tras Sprint 1 | Replay ambiente produjo falsos candidatos | Codex | Aceptada técnicamente |
| DEC-007 | 2026-08-24 | Adoptar quorum 3 y descartar quorum 2 | El quorum 2 duplicó eventos y falló ventanas de evaluación | Codex | Aceptada técnicamente |
| DEC-008 | 2026-08-24 | Mantener No-Go tras Sprint 2 | Latencia media 56.552 s y corpus insuficiente | Codex | Aceptada técnicamente |
| DEC-009 | 2026-08-26 | Redis Streams será el bus del MVP | Redis ya es necesario y permite beta sin activar GCP | Codex | Aceptada técnicamente; PO revisa costo antes de nube |
| DEC-010 | 2026-08-26 | Todo push inicia en dry run auditable | Evitar alertas reales accidentales | Codex | Aceptada técnicamente |

## 8. Registro de impedimentos

| ID | Detectado | Impedimento | Impacto | Responsable de resolver | Próxima acción | Estado |
|---|---|---|---|---|---|---|
| IMP-001 | 2026-08-23 | Python no estaba disponible en el entorno activo | No se reejecutaban pruebas backend | Codex | Python 3.12.10 instalado y validado | Resuelto 2026-08-24 |
| IMP-002 | 2026-08-23 | API móvil apunta a dominio de ejemplo | AAB actual no es publicable | Codex | Crear ambiente beta en Sprint 6 | Abierto |
| IMP-003 | 2026-08-23 | Falta asesor sismológico formal | No se validan umbrales para uso público | Product Owner | Contactar universidad/experto | Abierto |
| IMP-004 | 2026-08-23 | Falta grupo cerrado suficiente | Retrasa elegibilidad Play | Product Owner | Reclutar antes de Sprint 6 | Abierto |
| IMP-005 | 2026-08-24 | Feed rápido SGC no conserva replays antiguos | Impide validar en vivo asociaciones históricas | Codex | Usar fixture contractual y catálogo archivado con atribución | Documentado |
| IMP-006 | 2026-08-26 | WSL 2 no está habilitado | Docker daemon no inicia; E2E Compose pendiente | Product Owner | Ejecutar `wsl --install` como administrador y reiniciar | Abierto |

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
