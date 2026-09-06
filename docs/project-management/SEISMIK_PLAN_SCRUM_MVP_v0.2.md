# SEISMIK — PLAN SCRUM DEL MVP EXPERIMENTAL

Versión: 0.2  
Fecha de emisión: 30 de agosto de 2026  
Estado: En ejecución — Sprint 4 en curso  
Horizonte: 10 sprints / 19 semanas  
Cadencia: Sprint 0 de 1 semana y los demás sprints de 2 semanas

## Control de versiones

| Versión | Fecha | Autor | Descripción | Aprobador | Estado |
|---|---|---|---|---|---|
| 0.1 | 2026-08-23 | Codex | Plan inicial para llevar Alfa 0.1 a MVP Experimental 1.0 | Product Owner | Pendiente |
| 0.2 | 2026-08-30 | Codex | Incorpora Sprint Añadido 1 (API Platform OAuth) y Sprint Añadido 2 (alertas funcionales, iOS y evolución cartográfica Android) | Product Owner | Pendiente de aprobación |

## 1. Objetivo

Entregar un MVP experimental para Colombia capaz de ingerir señales sísmicas,
detectar candidatos en modo sombra, correlacionarlos con reportes oficiales,
enviar notificaciones de prueba a un grupo Android cerrado y recibir reportes
textuales que funcionen temporalmente sin conexión.

## 2. Roles y responsabilidades

| Rol | Responsable | Responsabilidades |
|---|---|---|
| Product Owner | Usuario/promotor | Visión, prioridades, presupuesto, aceptación, alianzas, cuentas, pruebas personales y decisiones Go/No-Go |
| Arquitecto y desarrollador | Codex | Diseño, implementación, pruebas automatizadas, documentación, CI/CD y evidencia técnica |
| Scrum Master operativo | Codex | Tablero, riesgos, impedimentos, definición de listo/terminado y reporte de Sprint |
| Validador científico | Por vincular — Product Owner gestiona | Revisión de ondas, picks, umbrales, métricas y limitaciones |
| Testers Android | Product Owner recluta | Instalación, pruebas en dispositivos, permisos, conectividad y retroalimentación |
| Revisión compartida | Product Owner + Codex | Sprint Review, aceptación, cambios de alcance y priorización del backlog |

## 3. Reglas de trabajo

- Un Sprint no cambia de objetivo después de iniciarse salvo riesgo crítico.
- Todo cambio de alcance entra al Product Backlog y se prioriza en la siguiente planificación.
- Ninguna alerta pública real forma parte de estos sprints.
- Toda notificación de ejercicio incluye `TEST` o `SIMULACRO`.
- Codex no activa pagos, publicaciones o compromisos institucionales sin autorización puntual.
- El Product Owner no debe compartir tarjetas, contraseñas o secretos por chat.

## 4. Ceremonias

| Ceremonia | Frecuencia | Duración | Resultado |
|---|---|---:|---|
| Sprint Planning | Inicio de cada Sprint | 45 min | Objetivo, tareas y dependencias confirmadas |
| Seguimiento | Dos veces por semana | 10–15 min | Estado, impedimentos y siguiente acción |
| Refinamiento | Mitad del Sprint | 30 min | Backlog siguiente preparado |
| Sprint Review | Final del Sprint | 45 min | Demostración y aceptación/rechazo |
| Retrospectiva | Final del Sprint | 20 min | Una mejora de proceso obligatoria |
| Revisión de riesgos/costos | Semanal desde despliegue | 15 min | Riesgos y pronóstico mensual actualizados |

## 5. Definiciones

### Definition of Ready

Una historia está lista cuando tiene objetivo, responsable, dependencia,
criterios de aceptación, datos de prueba y no requiere una decisión financiera o
externa pendiente.

### Definition of Done

Una tarea está terminada cuando:

- El código está versionado y no contiene secretos.
- Las pruebas aplicables pasan.
- La documentación y el README están actualizados.
- Existe evidencia enlazada en el control de avance.
- Se revisaron seguridad, privacidad y costo proporcionalmente al cambio.
- El Product Owner acepta los entregables que requieren validación humana.

## 6. Resumen de sprints

| Sprint | Semanas | Objetivo | Responsable primario | Entregable | Puerta de control |
|---|---:|---|---|---|---|
| 0 | 1 | Línea base y gobierno | Codex + Product Owner | Baseline Alfa 0.1 y backlog aprobado | Alcance y Git aceptados |
| 1 | 2–3 | Ingesta y replay reproducible | Codex | Detector de laboratorio | Replay y reconexión demostrados |
| 2 | 4–5 | Detección y correlación | Codex + asesor | Detector en modo sombra | Métricas revisadas, sin alertas públicas |
| 3 | 6–7 | API, bus y seguridad | Codex | Pipeline backend integrado | Pruebas extremo a extremo locales |
| 4 | 8–9 | Android y reportes offline | Codex + Product Owner | Build interno Android | Flujo probado en teléfonos reales |
| 5 | 10–11 | Push y simulacro cerrado | Codex + testers | Drill end-to-end | Notificación TEST trazable |
| 6 | 12–13 | Despliegue y shadow run | Codex + Product Owner | Piloto cloud controlado | 14 días de telemetría iniciados |
| 7 | 14–15 | Aceptación MVP | Equipo | MVP Experimental 1.0 | Decisión Go/No-Go documentada |
| Añadido 1 | 16–17 | API Platform moderna con OAuth | Codex + Product Owner | devs.seismik.org funcional | Alta, uso y revocación de claves demostrados |
| Añadido 2 | 18–19 | Alertas funcionales, iOS y experiencia cartográfica | Codex + Product Owner + asesor | Beta multiplataforma cerrada | Simulacro E2E y revisión científica aprobados |

### Estado actual del proyecto

El proyecto está en el **Sprint 4 — Aplicación Android y reporte offline mínimo**.
Los Sprints 1, 2 y 3 tienen cierre técnico; Sprint 4 está avanzado, pero aún no
cumple todos sus criterios de cierre porque faltan la sincronización offline
completa, la validación en dos teléfonos y la estabilización del entorno beta.
El Sprint Añadido 1 quedó desplegado y el Sprint Añadido 2 está implementado;
ambos conservan puertas de control abiertas y ninguno autoriza alertas
públicas certificadas.

## 7. Sprint 0 — Línea base, alcance y gobierno

Objetivo: convertir el código existente en un proyecto controlable y auditable.

| ID | Tarea | Responsable | Entregable | Dependencia | Criterio de aceptación |
|---|---|---|---|---|---|
| S0-01 | Crear documento maestro y plan Scrum | Codex | Word + fuentes Markdown | Ninguna | Documentos accesibles y versionados |
| S0-02 | Definir alcance dentro/fuera del MVP | Product Owner + Codex | Alcance aprobado | S0-01 | Product Owner registra decisión |
| S0-03 | Auditar `.gitignore` y secretos | Codex | Informe y exclusiones | Ninguna | Credenciales no aparecen en staging |
| S0-04 | Crear primer commit | Codex | Baseline Alfa 0.1 | S0-03 | Árbol limpio tras commit |
| S0-05 | Crear backlog, riesgos y control | Codex | Documento de control | S0-01 | IDs, estados y evidencia definidos |
| S0-06 | Confirmar presupuesto y cuentas | Product Owner | Tope beta registrado | S0-02 | Límite mensual aprobado; sin activar nube todavía |

Punto de chequeo: Sprint Review documental y confirmación de que no se presentará
el prototipo como sistema certificado.

## 8. Sprint 1 — Ingesta SeedLink y replay

Objetivo: hacer que la adquisición y reproducción sean deterministas y medibles.

| ID | Tarea | Responsable | Entregable | Dependencia | Criterio de aceptación |
|---|---|---|---|---|---|
| S1-01 | Instalar/fijar Python 3.12 y dependencias | Codex | Entorno reproducible | S0-04 | `pytest`, Ruff y mypy ejecutables |
| S1-02 | Verificar estaciones colombianas y canales | Codex | Catálogo fechado | Internet | Disponibilidad y lag registrados |
| S1-03 | Robustecer reconexión, buffer y gap handling | Codex | Cliente SeedLink | S1-01 | Recupera corte simulado sin bloquearse |
| S1-04 | Incorporar replay Mini-SEED histórico | Codex | Runner de replay | Datos abiertos | Ejecución repetible con timestamps controlados |
| S1-05 | Preparar mínimo tres casos históricos y ruido | Codex + asesor | Dataset/manifest | Licencias de datos | Fuente y hash de cada caso documentados |
| S1-06 | Ejecutar pruebas unitarias backend | Codex | Reporte de pruebas | S1-01 | Suite sin fallos o excepciones justificadas |

Punto de chequeo: demostración de flujo en vivo y replay; registrar pérdidas,
latencia de adquisición y estaciones inestables.

## 9. Sprint 2 — Detección y correlación científica

Objetivo: obtener candidatos auditables sin emitir alertas públicas.

| ID | Tarea | Responsable | Entregable | Dependencia | Criterio de aceptación |
|---|---|---|---|---|---|
| S2-01 | Parametrizar filtro, STA/LTA y sampling | Codex | Configuración por red | Sprint 1 | Cada parámetro tiene unidad y justificación |
| S2-02 | Validar coincidencia multiestación y geometría | Codex | Coincidence engine | S2-01 | No confirma con una sola estación |
| S2-03 | Medir verdaderos/falsos positivos en replay | Codex | Matriz de resultados | S1-05 | Resultados reproducibles, sin ocultar fallos |
| S2-04 | Ajustar correlación SGC por tiempo/distancia | Codex + asesor | Matcher regional | Fuente SGC | Casos de borde probados y umbral documentado |
| S2-05 | Implementar salud y lag por estación | Codex | Métricas de estación | S1-03 | Estación atrasada no cuenta silenciosamente |
| S2-06 | Revisión sismológica | Product Owner gestiona; asesor revisa | Acta técnica | Asesor disponible | Limitaciones y siguiente calibración registradas |

Punto de chequeo: no se exige una tasa científica arbitraria; se exige medición,
trazabilidad y aprobación explícita antes de cambiar de modo sombra.

## 10. Sprint 3 — API, bus durable y seguridad

Objetivo: cerrar el pipeline backend en ambiente local y preparar despliegue.

| ID | Tarea | Responsable | Entregable | Dependencia | Criterio de aceptación |
|---|---|---|---|---|---|
| S3-01 | Consolidar esquemas Pydantic y contratos | Codex | OpenAPI versionada | Sprint 2 | Candidate y official-update validados |
| S3-02 | Probar HMAC, replay protection e idempotencia | Codex | Seguridad de ingesta | S3-01 | Casos negativos automatizados |
| S3-03 | Definir bus MVP: Redis o Pub/Sub | Codex propone; PO aprueba costo | ADR | Presupuesto | Decisión y migración documentadas |
| S3-04 | Verificar App Check y registro | Codex | Device onboarding | Firebase | Tokens inválidos rechazados |
| S3-05 | Integrar dispatcher FCM desactivado por defecto | Codex | Worker | S3-03 | Solo envía a lista de testers |
| S3-06 | Prueba local extremo a extremo | Codex | Evidencia E2E | S3-01..05 | Replay produce evento, cola y payload TEST |
| S3-07 | Preparar IaC, cuotas y límites | Codex | Configuración de despliegue | ADR nube | No crea recursos sin autorización |

Punto de chequeo: decidir si activar la prueba GCP justo antes del primer despliegue,
para no consumir días del crédito mientras el sistema continúa local.

## 11. Sprint 4 — Aplicación Android y reporte offline mínimo

Objetivo: entregar la experiencia móvil incluida en el MVP.

| ID | Tarea | Responsable | Entregable | Dependencia | Criterio de aceptación |
|---|---|---|---|---|---|
| S4-01 | Conectar app a API de ambiente de prueba | Codex | Configuración segura | Sprint 3 | No usa dominio `.example` en build interno |
| S4-02 | Integrar mapa base y capas Seismik | Codex | MonitorScreen | Clave restringida si usa Google Maps | Estaciones y eventos se distinguen claramente |
| S4-03 | Completar detalle oficial y fuentes | Codex | EventDetail | S3-01 | Fuente y estado provisional/oficial visibles |
| S4-04 | Reporte “lo sentí” | Codex | Flujo móvil | API reporting | Envío firmado e idempotente |
| S4-05 | Reporte textual de daño/peligro | Codex | Formulario mínimo | API reporting | Sin fotos/video; advertencia de emergencias |
| S4-06 | Cola local offline y sincronización | Codex | Store-and-forward | S4-04/05 | Reintenta sin duplicar; muestra enviado/pendiente |
| S4-07 | Prueba en 2+ teléfonos Android | Product Owner + testers | Evidencia de dispositivo | Builds | Permisos, reinicio y red intermitente probados |

Punto de chequeo: el Product Owner acepta claridad, accesibilidad, privacidad y
comportamiento sin Internet.

## 12. Sprint 5 — Push y simulacro extremo a extremo

Objetivo: demostrar una alerta experimental cerrada, inequívocamente marcada.

| ID | Tarea | Responsable | Entregable | Dependencia | Criterio de aceptación |
|---|---|---|---|---|---|
| S5-01 | Canal Android de alta prioridad | Codex | NotificationService | Sprint 4 | Permisos y degradación documentados |
| S5-02 | Overlay y guía de seguridad | Codex | AlertOverlay | S5-01 | Solo payload autorizado abre overlay |
| S5-03 | Modo simulacro con doble protección | Codex | Drill mode | Backend | `TEST` visible en payload, título, UI y log |
| S5-04 | Medir timestamps del pipeline | Codex | Dashboard de latencia | S5-03 | P50/P95 por etapa disponibles |
| S5-05 | Ejecutar simulacro cerrado | Product Owner autoriza; Codex ejecuta | Acta de simulacro | Testers informados | Cero destinatarios fuera de allowlist |
| S5-06 | Recoger retroalimentación | Product Owner | Registro de hallazgos | S5-05 | Hallazgos priorizados para Sprint 6 |

Punto de chequeo: cualquier notificación a personas requiere confirmación puntual
del Product Owner y aviso previo a los testers.

## 13. Sprint 6 — Despliegue controlado y operación en sombra

Objetivo: operar el MVP en nube con costos y riesgos limitados.

| ID | Tarea | Responsable | Entregable | Dependencia | Criterio de aceptación |
|---|---|---|---|---|---|
| S6-01 | Activar GCP y vincular facturación | Product Owner, guiado por Codex | Cuenta de prueba | Sprint 3 listo | Product Owner completa datos y confirma acción final |
| S6-02 | Desplegar detector y API | Codex | Entorno beta | S6-01 | Health checks y rollback probados |
| S6-03 | Configurar secretos, IAM y App Check | Codex | Seguridad cloud | S6-02 | Mínimo privilegio y credenciales fuera de imágenes |
| S6-04 | Configurar cuotas, máximos y alertas | Codex | Guardas de costo | S6-01 | Pronóstico ≤150.000 COP/mes |
| S6-05 | Configurar logs, métricas y runbook | Codex | Observabilidad | S6-02 | Alarmas de caída, lag y cola verificadas |
| S6-06 | Iniciar 14 días de modo sombra | Codex monitorea; PO revisa | Shadow run | S6-02..05 | Sin push público; incidentes registrados |
| S6-07 | Reclutar grupo cerrado Play | Product Owner | Lista de testers | Cuenta Play | Cumple requisito vigente de la consola |

Punto de chequeo: revisión diaria inicial de salud y semanal de costos; ningún
problema de detector se “corrige” alterando datos históricos sin trazabilidad.

## 14. Sprint 7 — Prueba cerrada y aceptación del MVP

Objetivo: tomar una decisión basada en evidencia.

| ID | Tarea | Responsable | Entregable | Dependencia | Criterio de aceptación |
|---|---|---|---|---|---|
| S7-01 | Construir AAB definitivo firmado | Codex | Release candidate | Sprint 6 | API real, secretos externos y firma verificada |
| S7-02 | Subir a prueba cerrada | Product Owner autoriza; Codex asiste | Track cerrado | S7-01 | No es producción pública |
| S7-03 | Completar ciclo de testers | Product Owner + testers | Evidencia Play | S7-02 | Duración y cantidad exigidas por Play |
| S7-04 | Analizar shadow run y simulacro | Codex + asesor | Informe MVP | S6-06 | Latencia, disponibilidad y errores publicados |
| S7-05 | Revisar privacidad, seguridad y costos | Codex + Product Owner | Checklist | Datos reales de beta | Sin hallazgo crítico ignorado |
| S7-06 | Decisión Go/No-Go | Product Owner | Acta firmada | S7-03..05 | Aceptar, extender o detener con razones |
| S7-07 | Versionar MVP 1.0 o nueva alfa | Codex | Tag y release notes | S7-06 | Versión coincide con decisión |

Punto de chequeo: “Go” significa continuar a piloto institucional; no autoriza
alertas públicas certificadas ni automatización física.

## 15. Sprint Añadido 1 — API Platform moderna con OAuth

Objetivo: convertir `devs.seismik.org` en el portal independiente y seguro desde
el que investigadores, universidades y empresas puedan conocer, solicitar y
administrar acceso gratuito inicial a las APIs de Seismik.

| ID | Tarea | Responsable | Entregable | Dependencia | Criterio de aceptación |
|---|---|---|---|---|---|
| SA1-01 | Separar portal, web pública y API por hostname | Codex | devs.seismik.org, seismik.org y api.seismik.org | DNS/TLS estable | Cada hostname sirve únicamente su función y usa HTTPS válido |
| SA1-02 | Implementar acceso OAuth con Google/Firebase | Codex; Product Owner autoriza cuenta | Inicio y cierre de sesión | Firebase Auth | Solo una identidad verificada puede entrar al panel privado |
| SA1-03 | Crear panel moderno de productos API | Codex | Catálogo y documentación interactiva | Contratos OpenAPI | Servicios, alcance, estado y ejemplos son comprensibles |
| SA1-04 | Crear ciclo de vida de claves | Codex | Crear, mostrar una vez, rotar y revocar claves | SA1-02 | El servidor conserva solo el hash y una clave revocada deja de funcionar |
| SA1-05 | Aplicar cuotas, rate limiting y auditoría | Codex; Product Owner aprueba política | Plan gratuito inicial | Redis y observabilidad | Abuso limitado, consumo visible y límites documentados |
| SA1-06 | Proteger endpoints y separar accesos internos | Codex | Autorización por producto/alcance | SA1-04 | Sin clave válida no se exponen datos protegidos; salud pública mínima permanece operable |
| SA1-07 | Publicar términos, privacidad y soporte | Product Owner define; Codex implementa | Textos y flujo de aceptación | Revisión legal pendiente | Usuario acepta versión fechada antes de crear una clave |
| SA1-08 | Ejecutar prueba E2E y revisión de seguridad | Codex | Evidencia reproducible | SA1-01..07 | Login, alta, consumo, cuota, rotación y revocación pasan; no se filtran secretos |

Punto de chequeo: demostración completa desde una cuenta nueva hasta una llamada
autorizada a la API. La gratuidad inicial no elimina cuotas, trazabilidad ni la
posibilidad de suspender una clave abusiva.

## 16. Sprint Añadido 2 — Alertas funcionales, iOS y mapas móviles

Objetivo: demostrar en un grupo cerrado alertas sísmicas de extremo a extremo
alimentadas por estaciones reales, con aplicaciones Android e iOS funcionales y
una experiencia cartográfica coherente, sin declarar todavía un sistema público
certificado.

| ID | Tarea | Responsable | Entregable | Dependencia | Criterio de aceptación |
|---|---|---|---|---|---|
| SA2-01 | Estabilizar conexiones SeedLink y proveedores por región | Codex + asesor científico | Red de adquisición con fallback | Salud de estaciones | Reconexión, latencia, pérdida y cambio de proveedor quedan medidos |
| SA2-02 | Calibrar confirmación multiestación y reglas de riesgo | Codex + asesor científico | Perfil de alertamiento versionado | Replays y modo sombra | Ruido local no dispara; reglas territoriales y umbrales quedan justificados |
| SA2-03 | Activar pipeline de alertas en grupo cerrado | Codex; Product Owner autoriza simulacro | Candidate → bus → push → móvil | Sprint 5 y Firebase/APNs | Payload trazable llega solo a allowlist y cumple filtros del usuario |
| SA2-04 | Completar preferencias de notificación | Codex | Configuración persistente | Registro de dispositivos | Usuario selecciona magnitud mínima, distancia, regiones y tipos de actualización |
| SA2-05 | Construir app iOS con lenguaje Liquid Glass | Codex | Beta iOS equivalente a Android | Cuenta Apple y equipo de prueba | Navegación, accesibilidad, alertas y reportes funcionan en iPhone real compatible |
| SA2-06 | Permitir Apple Maps o Google Maps en iOS | Codex | Selector de proveedor cartográfico | Claves y SDK aplicables | Preferencia se conserva y ambos proveedores muestran el mismo epicentro |
| SA2-07 | Completar Historial/Recientes Android como mapa | Codex | Mapa interactivo de pantalla completa | Catálogo oficial | El mapa se desplaza y amplía sin bloqueos; marcadores y estado de fuente son visibles |
| SA2-08 | Añadir panel inferior deslizable tipo “Para ti” | Codex | Hoja inferior de eventos | SA2-07 | Se arrastra arriba/abajo, conserva el mapa operable y selecciona un evento |
| SA2-09 | Añadir “Abrir en Google Maps” por sismo | Codex | Acción externa de epicentro | Coordenadas válidas | Abre Google Maps en las coordenadas; ofrece fallback web si no está instalada |
| SA2-10 | Ejecutar shadow run y simulacro multiplataforma | Codex + Product Owner + testers + asesor | Evidencia Android/iOS | SA2-01..09 | Latencia, entrega, fallos y falsos disparos quedan registrados y revisados |

Punto de chequeo: revisión científica y simulacro cerrado en Android e iOS. La
activación pública, las Critical Alerts de Apple y cualquier afirmación de alerta
temprana operativa requieren aprobaciones externas y una decisión Go/No-Go aparte.

## 17. Product Backlog posterior al MVP ampliado

| Prioridad | Épica | Fase propuesta |
|---:|---|---|
| 1 | Piloto con universidad y revisión científica ampliada | Piloto institucional |
| 2 | Dashboard Seismik Monitor | Piloto institucional |
| 3 | Reportes offline por QR y app Responder | Respuesta resiliente |
| 4 | Fotos comprimidas, cuarentena y ciclo de vida | Respuesta resiliente |
| 5 | SMS mediante acuerdo con operador | Respuesta resiliente |
| 6 | Gateway con batería y enlace redundante | Respuesta resiliente |
| 7 | Cobertura regional/mundial progresiva | Expansión |
| 8 | Planes institucionales y exportaciones de investigación | Expansión |
| 9 | IoT supervisado con fabricante | IoT seguro |

## 18. Métricas del proyecto

- Burn-up: historias aceptadas frente al alcance total.
- Porcentaje de tareas bloqueadas y antigüedad del bloqueo.
- Cobertura y resultado de pruebas por componente.
- Latencia SeedLink, detector, bus, dispatcher y dispositivo.
- Salud, lag y disponibilidad por estación.
- Falsos positivos y falsos negativos sobre datasets etiquetados.
- Reportes offline sincronizados y duplicados evitados.
- Costo real y pronosticado mensual.
- Defectos encontrados por testers y tiempo de resolución.
- Riesgos críticos abiertos.

## 19. Aprobación

| Rol | Decisión | Fecha | Observaciones |
|---|---|---|---|
| Product Owner | Pendiente | Pendiente | Aprobar el horizonte ampliado de diez sprints y responsabilidades |
| Responsable técnico | Actualizado | 2026-08-30 | Sprint 4 en curso; Sprint Añadido 1 desplegado; Sprint Añadido 2 implementado con simulacro multiplataforma y revisión científica pendientes |
