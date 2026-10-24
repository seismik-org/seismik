# Grupo Seismik y pies de página — 2026-10-23

La dirección pública canónica sigue siendo https://seismik.org/grupo/.
`group.seismik.org` no resolvía DNS durante esta revisión; los enlaces de los
portales no dependen de ese subdominio. No se han creado registros DNS.

## Cambios

- Grupo: cuadrículas resistentes a desbordamientos, foco visible, separación
  respecto de la cabecera fija y directorio de portales. Se conservan Jade,
  PortiPaq, sus destinos oficiales y las limitaciones de la beta sísmica.
- Todos los HTML de `web/` y `waves/static/` incluyen un enlace absoluto en el
  pie, también las páginas de error y sin conexión, sin necesitar JavaScript.
- Los iconos nuevos tienen tamaño explícito en HTML: una hoja CSS antigua en
  la caché no puede convertirlos en flechas gigantes.
- Se regeneraron Status, el respaldo del Worker y la versión del service worker.

## Publicación verificada

- Cloud Run web: `seismik-web-00061-4n4`, 100 % del tráfico.
- Imagen: `us-east1-docker.pkg.dev/seismik-15bbb/seismik/web:group-footer-20261023-r2`.
- Cloud Build: `e8e5f727-b175-49cd-9c95-11ceca384578`, SUCCESS.
- Worker principal `seismik`: `0214e8bd-90f1-4ee3-b2d7-9f7fd35a6539`.
- Worker Waves: `b0c50e61-2d00-4361-89d2-3dc9318504cc`.
- Antes de publicar se comparó el router del Worker activo con el código local:
  idéntico, al igual que `status-history.js`. Sólo cambian los recursos del pie.
- Waves conserva los recursos del suplemento ya desplegado (fuente local
  `f5a1ae4` en `work/seismik-mobile-adaptive`); no se sustituyó por el archivo
  anterior de `main`. Se subieron sólo cuatro recursos estáticos: HTML de
  inicio/exploración/404 y `brand.css`. El backend y los datos privados no cambian.
- No se desplegaron API, detector, dispatcher ni aplicaciones móviles.

## Comprobaciones

47 pruebas de Node aprobadas, incluidas regresiones de enlaces en todos los
pies, recursos locales del grupo, iconos con CSS antiguo y recursos del borde.
Comprobación HTTP 200 y enlace al grupo en portada, Grupo, Developers, Auth
(`/id`), Status, Ifeltit, Waves, exploración, Contacto y página sin conexión.
Revisión visual de la página publicada en navegador.

## Reversión

- Web: devolver el tráfico a `seismik-web-00059-l7j`.
- Worker principal anterior: `db680d88-5b7a-4608-8902-756288ebb266`.
- Waves anterior a este trabajo: `388a9ecf-f7f9-4c3a-8b61-db8303abfc40`
  (última versión documentada antes de este cambio; comprobar despliegues antes
  de revertir si hubo otras publicaciones).
