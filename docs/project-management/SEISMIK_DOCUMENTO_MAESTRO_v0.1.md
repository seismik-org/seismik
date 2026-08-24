# SEISMIK — DOCUMENTO MAESTRO DEL PROYECTO

Versión: 0.1  
Fecha de emisión: 23 de agosto de 2026  
Estado: Borrador para aprobación  
Propietario del producto: Promotor de Seismik  
Responsable técnico: Codex  
Clasificación: Proyecto abierto — información de planificación

## Control de versiones

| Versión | Fecha | Autor | Descripción | Aprobador | Estado |
|---|---|---|---|---|---|
| 0.1 | 2026-08-23 | Codex | Documento maestro inicial y definición honesta del MVP | Product Owner | Pendiente |

## 1. Resumen ejecutivo

Seismik es una plataforma abierta de detección sísmica, notificación experimental,
consolidación de información oficial y recepción de reportes ciudadanos. Integra
estaciones sismológicas abiertas mediante SeedLink, procesamiento con ObsPy,
detección STA/LTA y coincidencia multiestación. El ecosistema contempla una API
FastAPI, mensajería durable, despacho FCM/APNs y una aplicación Flutter.

El estado actual se clasifica como **Prototipo Alfa 0.1**, no como un sistema de
alerta pública certificado. El primer objetivo verificable será un **MVP
Experimental 1.0 para Colombia**, operado en modo sombra y con usuarios de prueba
controlados. El proyecto no afirmará que predice sismos ni garantizará alertas.

## 2. Problema y oportunidad

Las fuentes oficiales posteriores al sismo son indispensables, pero normalmente
no constituyen por sí mismas una alerta temprana. A su vez, una aplicación móvil
aislada no resuelve cobertura de estaciones, validación científica, conectividad
de emergencia ni coordinación institucional.

Seismik busca integrar en una plataforma auditable:

- Detección experimental directa desde estaciones abiertas.
- Confirmación y actualización posterior desde agencias oficiales.
- Reportes ciudadanos de percepción, daños y peligros.
- Datos anonimizados para investigación.
- Preparación futura para gateways de emergencia e IoT institucional.

## 3. Propuesta de valor

- Núcleo abierto, auditable y reproducible.
- Integración de estaciones profesionales, fuentes oficiales y participación ciudadana.
- Capacidad de despliegue académico e institucional.
- Reportes offline-first en fases posteriores.
- API de investigación y servicios administrados como fuente de sostenibilidad.
- Posibilidad futura de integración segura con infraestructura física.

La alerta ciudadana básica deberá permanecer gratuita. Los ingresos provendrán de
pilotos, operación administrada, soporte, analítica, capacitación, integraciones
institucionales e IoT validado.

## 4. Estado actual verificado

| Área | Estado | Evidencia actual | Brecha principal |
|---|---|---|---|
| Backend sísmico | Implementado como prototipo | `src/eew/` y pruebas unitarias existentes | Falta entorno Python activo, calibración y prueba continua real |
| API y bus | Implementados localmente | `src/api/`, Redis Streams y Docker Compose | No existe despliegue productivo ni URL real |
| App Flutter | Compilable | Análisis sin errores y 2 pruebas aprobadas | Cobertura de pruebas insuficiente y backend de ejemplo |
| Android/Firebase | Configuración inicial | Proyecto Firebase y aplicación Android registrados | Falta App Check productivo y prueba push extremo a extremo |
| Play Store | Ficha creada | Aplicación Seismik en Play Console | Falta AAB definitivo y prueba cerrada requerida |
| Fuentes oficiales | Catálogo configurado | `official_sources.json` | Falta vigilancia continua, términos y ajuste regional de correlación |
| Reportes ciudadanos | Flujo básico implementado | Percepción y daño textual | Falta cola offline; multimedia se aplaza |
| Operación | No desplegada | Configuración local | Faltan observabilidad, runbooks, redundancia y guardas de costo |
| Versionamiento | Preparado | Repositorio Git en rama `main` | Antes de este documento no existía commit base |

## 5. Definición del MVP Experimental 1.0

### 5.1 Incluido

- Android como primera plataforma móvil.
- Colombia como primera región operativa.
- Conexión real a estaciones SeedLink disponibles y monitorizadas.
- Búfer, reconexión y procesamiento determinista de formas de onda.
- STA/LTA y coincidencia de al menos tres estaciones configurables.
- Reproducción de registros Mini-SEED históricos.
- Modo sombra sin alerta pública automática.
- Correlación posterior con SGC y fuentes complementarias autorizadas.
- API firmada, registro de dispositivos y bus durable.
- Notificaciones de simulacro y eventos experimentales solo a testers autorizados.
- Mapa, estado de red, eventos recientes y detalle oficial.
- Reporte “lo sentí” y reporte textual de daño/peligro.
- Cola offline para el reporte mínimo, sin fotografías ni videos.
- Observabilidad, medición de latencia, auditoría y límites de gasto.
- Prueba cerrada y decisión formal Go/No-Go.

### 5.2 Excluido

- Fotografías y videos ciudadanos.
- Despliegue iOS y Critical Alerts de Apple.
- Cobertura mundial operativa.
- Alertas críticas automáticas al público general.
- Activación autónoma basada solo en acelerómetros móviles.
- SMS, Bluetooth mesh, enlaces satelitales y gateways comunitarios.
- Automatización de gas, energía, agua, ascensores o maquinaria.
- SLA comercial o certificación de protección civil.
- Alta disponibilidad multirregional.

## 6. Usuarios y partes interesadas

| Actor | Necesidad | Participación en el MVP |
|---|---|---|
| Ciudadano tester | Información clara y reporte simple | Prueba controlada, sin promesa de alerta certificada |
| Universidad | Datos reproducibles y acceso técnico | Socio recomendado para calibración y piloto |
| Sismólogo asesor | Validación de señales y umbrales | Revisión científica requerida antes de alertas públicas |
| Brigada o gestor de riesgo | Visibilidad de eventos y daños | Entrevistas y validación de flujo textual |
| Product Owner | Prioridad, financiación y alianzas | Decide alcance, acepta entregables y autoriza servicios externos |
| Codex | Ingeniería y documentación | Implementa, prueba, documenta y presenta evidencia |

## 7. Arquitectura objetivo del MVP

```text
Estaciones SeedLink
        ↓
Detector Python/ObsPy 24x7
        ↓ evento candidato firmado
API FastAPI → bus durable → dispatcher FCM
        ↓                         ↓
Fuentes oficiales            Android testers
        ↓                         ↓
Actualización oficial ← reportes de percepción y daños
```

El detector continuo se ejecutará en una VM o entorno equivalente. La API HTTP
podrá ejecutarse en Cloud Run. Kubernetes y TPU quedan fuera del MVP.

## 8. Principios de seguridad y ética

- Un `earthquake_candidate` no equivale a confirmación oficial.
- Ningún disparo STA/LTA aislado genera una alerta pública.
- Todo simulacro debe incluir `TEST` de forma visible y auditable.
- Se minimizan ubicación precisa, identificadores y retención de datos.
- No se comercializan datos personales ni ubicaciones individuales.
- Las credenciales nunca se almacenan en Git ni en imágenes Docker.
- El usuario conserva control sobre permisos, notificaciones y participación.
- La automatización física futura requerirá gateway local, interbloqueos y validación.

## 9. Modelo de sostenibilidad inicial

| Portafolio | Momento | Forma de ingreso |
|---|---|---|
| Piloto académico | MVP | Proyecto de 3 meses y acompañamiento técnico |
| Capacitación y simulacros | MVP | Talleres institucionales marcados como ejercicio |
| Seismik Research | Después de datos suficientes | API, exportaciones y soporte académico |
| Seismik Monitor | Después del MVP | Suscripción por sede y operación administrada |
| Seismik Response | Fase posterior | Dashboard de daños y gateways resilientes |
| Seismik IoT | Fase avanzada | Integración, gateway y mantenimiento certificado |
| Patrocinios open source | Desde el inicio | Aportes comunitarios e institucionales transparentes |

## 10. Restricciones y supuestos

- Los proveedores SeedLink no garantizan todas las estaciones ni todos los países.
- La conectividad móvil y eléctrica puede fallar durante una emergencia.
- Android e iOS limitan la ejecución en segundo plano y alertas críticas.
- La operación pública requiere revisión científica, legal e institucional.
- El presupuesto beta objetivo será igual o inferior a 150.000 COP mensuales.
- Las decisiones de facturación y contratación requieren autorización del Product Owner.

## 11. Riesgos principales

| Riesgo | Probabilidad | Impacto | Tratamiento MVP |
|---|---|---|---|
| Falso positivo | Alta | Crítico | Modo sombra, coincidencia multiestación y replay |
| Evento no detectado | Media | Crítico | Métricas de sensibilidad y revisión sismológica |
| Estación fuera de servicio | Alta | Alto | Salud por estación, reconexión y proveedores múltiples |
| Factura inesperada | Media | Alto | Cuotas, máximos de instancias y revisión semanal de costo |
| Abuso de reportes | Media | Alto | App Check, rate limit, firma y moderación posterior |
| Falta de Internet | Alta en desastre | Alto | Cola offline mínima en MVP; relays en fase posterior |
| Rechazo de permisos móviles | Media | Alto | Funciones degradables y prueba en dispositivos reales |
| Falta de validación institucional | Media | Crítico | Buscar universidad y asesor sismológico desde el MVP |

## 12. Criterios de éxito del MVP

- Pipeline completo reproducible desde replay hasta notificación de prueba.
- Operación en sombra durante al menos 14 días con telemetría continua.
- Todos los eventos y decisiones contienen trazabilidad y timestamps.
- Reportes mínimos sobreviven pérdida de conectividad y sincronizan sin duplicarse.
- Build Android definitivo instalado por el grupo cerrado de testers.
- Sin secretos detectados en Git ni vulnerabilidades críticas conocidas sin tratamiento.
- Pronóstico mensual de infraestructura dentro del límite aprobado.
- Revisión científica documentada de resultados, aunque identifique brechas.
- Decisión Go/No-Go registrada; el MVP puede aceptarse como experimental sin autorizar alertas públicas.

## 13. Hoja de ruta escalable

| Fase | Objetivo | Elementos principales |
|---|---|---|
| Fase 0 | Prototipo Alfa 0.1 | Base de código, arquitectura y build de validación |
| Fase 1 | MVP Experimental 1.0 | Colombia, Android, modo sombra y reportes textuales offline |
| Fase 2 | Piloto institucional | Dashboard, asesoría científica, operación controlada y primera venta |
| Fase 3 | Respuesta resiliente | Fotos limitadas, QR, SMS acordado y gateways institucionales |
| Fase 4 | Expansión | iOS, nuevas regiones, proveedores y API Research |
| Fase 5 | IoT seguro | Gateways locales, fabricantes, certificación y pilotos supervisados |

## 14. Gobierno y decisiones

El Product Owner decide prioridad, presupuesto, aceptación, alianzas y cualquier
acción externa representativa o financiera. Codex prepara alternativas, implementa
el alcance autorizado, ejecuta pruebas y conserva evidencia. Una decisión de
publicar alertas o controlar infraestructura requiere una revisión adicional y no
se infiere de la aprobación de este documento.

## 15. Aprobación

| Rol | Nombre | Decisión | Fecha | Observaciones |
|---|---|---|---|---|
| Product Owner | Pendiente | Pendiente | Pendiente | Aprobar alcance del MVP |
| Responsable técnico | Codex | Elaborado | 2026-08-23 | Sujeto a revisión del Product Owner |

