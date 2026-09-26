# Protección gradual contra abuso web

Seismik debe usar **Cloudflare Managed Challenge**, no reCAPTCHA. El desafío
gestionado es adaptativo, evita añadir Google como procesador de datos y suele
ser invisible para visitas normales.

En Cloudflare → Security → WAF → Custom rules, crear y desplegar esta regla:

- Nombre: `Challenge suspicious portal scans`
- Expresión:
  ```
  (http.host in {"devs.seismik.org" "auth.seismik.org"} and
   (http.request.uri.path contains "/.env" or
    http.request.uri.path contains "/wp-" or
    http.request.uri.path contains "/php" or
    http.request.uri.path contains "/.git" or
    http.request.uri.path contains "/cgi-bin" or
    http.request.uri.path contains "/admin"))
  ```
- Acción: **Managed Challenge**.

No aplicar el desafío a `api.seismik.org`: los teléfonos y los webhooks no
pueden resolverlo. La API ya exige su secreto de origen y sus propios límites
de tasa. Revisar Security Events tras siete días antes de ampliar la regla.
