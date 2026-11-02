# Correcciones publicadas — 2026-11-02

Se publicaron correcciones de catálogo, cuotas por visitante, preparación del detector y supervisión de trabajadores. La publicación conserva las imágenes activas como bases inmutables y comprueba hashes antes de modificar archivos. No se reconstruyó producción íntegramente desde la rama antigua.

## Preservación y conciliación

- Respaldo previo: history.bundle con todas las referencias, parche y ZIP del árbol pendiente, con manifiesto SHA-256 en `outputs/seismik-before-fixes-20261102` del chat de trabajo.
- La rama original feature/liveahora-web permanece intacta. La rama de trabajo es fix/seismik-review-20261102.
- Se preservó el panel LiveAhora previamente sin commit y se integró origin/feat/family-web-improvements-20261101.
- Se recuperaron de las imágenes activas las funciones de cuenta, correo, borrado y las protecciones del detector que no figuraban en la rama antigua. Las pruebas se adaptaron a esas protecciones: diagnóstico explícito no genera alertas públicas, bitácora pública, integraciones ni ubicación familiar.
- Los secretos y las especificaciones completas de ejecución permanecieron privados en Cloud Shell. No se añadieron valores de credenciales a Git.
- Las correcciones publicadas usan archivos concretos sobre las imágenes originales: se mantienen activos los demás archivos, recursos científicos, configuración y credenciales de cada servicio. Los Dockerfiles y cargas exactas se conservan en el informe local; un build general futuro debe conciliar también los recursos ajenos a src antes de sustituir estas bases.

## Comportamiento corregido

- Las revisiones de un mismo reporte oficial se consolidan antes del filtro de magnitud; no se resucita una revisión antigua que superase el umbral.
- Una fila corrupta del stream no oculta el resto del catálogo. No se modifican los datos ni los identificadores de entrega almacenados.
- Las cuotas públicas distinguen visitantes a través del Worker autenticado. Una cabecera de visitante falsificada desde otro origen no se considera fiable.
- /health/ready del detector devuelve 503 ante cobertura degradada, inicialización o error de telemetría; /health/live conserva la comprobación del proceso. No se sustituyó su sonda TCP por readiness ni se relanzan instancias por una caída del proveedor.
- Si termina inesperadamente cualquiera de los dos consumidores combinados, el supervisor puede recuperar el conjunto; ya no queda el otro consumidor esperando indefinidamente.
- Staging/producción requieren el secreto de origen; se conservó el valor existente. Se corrigió la importación de Pub/Sub para el análisis de tipos.
- CI ejecuta todos los tests Node de tests y detecta cambios de runtime_health para los servicios que lo usan.

## Revisiones activas comprobadas

| Servicio | Revisión nueva | Tráfico | Revisión de reversión |
|---|---|---|---|
| seismik-api | seismik-api-review-fixes-1102 | 100 % | seismik-api-family-1101-bounded |
| seismik-detector | seismik-detector-review-fixes-1102 | 100 % | seismik-detector-00007-2b4 |
| seismik-dispatcher | seismik-dispatcher-review-fixes-1102 | 100 % | seismik-dispatcher-00059-crl |

Proyecto seismik-15bbb, región us-east1. Se compararon especificaciones antes/después: mismas variables, referencias a secretos, identidad, recursos, sondas, volúmenes y límites de escala. La web conserva su revisión seismik-web-family-1101-final. No se alteraron DNS, IAM, Firestore ni reglas Cloudflare en esta publicación.

Imágenes nuevas:

- API: sha256:6a540d88399c24f471e67bf7402098b7c9f2b7353cc68c7905e463bfd60d49c8
- Detector: sha256:e37dd5ed1f89545352dc3485b773875d88297130f24b5089842b9e75a8e19f50
- Dispatcher: sha256:844e9cbd67c76cc3e4f1ab93b59bfbd91a8f0fc3cb82673bc0fd0e498d464d56

Cloud Build us-east1: API 3788e771-6d2e-40d8-92e8-da77bb40c0bc; trabajadores 0d679701-be75-4bc5-b274-89d3c667901e. Ambos SUCCESS; los parches verificaron sus bases y los módulos modificados compilaron.

Para revertir un servicio, tras comprobar su estado actual: `gcloud run services update-traffic SERVICIO --to-revisions=REVISION_ANTERIOR=100 --project=seismik-15bbb --region=us-east1`. Las revisiones anteriores no se eliminaron.

## Validación

- 787 pruebas Python correctas tras la conciliación; Ruff correcto y mypy sin incidencias en 95 módulos.
- 58 pruebas Node correctas. Flutter móvil: 186; Wear: 36; ambos analyze sin incidencias. No se distribuyeron binarios de tiendas.
- En la revisión aislada de API: liveness y readiness 200, catálogo y LiveAhora 200, panel y sesión sin autenticación 401. No hubo escritura de eventos, avisos, informes ciudadanos ni correo de prueba.
- Después de publicar: las tres revisiones Ready y 100 % de tráfico; dispatcher readiness 200; detector liveness autenticado 200. API pública, portada y /admin de LiveAhora y Grupo responden 200. Navegador integrado: la portada usa el catálogo actualizado, sin las revisiones antiguas repetidas de los mismos identificadores oficiales.
- El detector informó cobertura degradada: 12 de 25 estaciones sanas en la muestra, Colombia 7/15, Chile 3/4, Indonesia 0/3 y Europa central 2/3. Es una muestra temporal; quorum no equivale a cobertura completa. /health/ready devuelve 503 deliberadamente ante esta situación. No se rebajaron los criterios para presentar verde.
- El único registro ERROR hallado en la ventana examinada era la petición 503 a /health/ready de nuestra comprobación; no una excepción de aplicación. La ventana y el límite de consulta no acreditan ausencia histórica de errores.

## Pendientes y límites

Permanecen la recuperación real de las ondas transferidas, la contraseña Android cifrada con DPAPI de otro contexto, la validación científica independiente y la disponibilidad de las fuentes/estaciones incompletas, incluido SGC desactivado. No se sustituyeron claves ni se habilitaron avisos públicos experimentales.

La suite adicional de Waves, fuera de testpaths principal, produjo 11 fallos y 34 éxitos al faltar los catálogos/previsualizaciones generados e ignorados por Git en este PC. No se reemplazaron con un snapshot antiguo ni se desplegó Waves. Las pruebas principales no acreditan restauración del archivo de ondas, entrega push en hardware, carga máxima, firma de tiendas o revisión integral de CVE/IAM.

El presupuesto existente de 180.000 COP/mes y sus alertas permanecen como se configuraron antes; un presupuesto con alertas no es un tope de consumo.
