# Verificación de marca de Google para el acceso con Google

Google rechazó la verificación con este motivo:

> El sitio web de la URL de tu página principal "https://seismik.org" no está
> registrado a tu nombre. Verifica la propiedad de tu página principal.

No es un problema del contenido de la web. Google exige que la cuenta dueña del
proyecto de OAuth demuestre que también controla el dominio de la página
principal, y esa prueba se hace en Search Console, fuera de este repositorio.

## Qué hay que verificar exactamente

El proyecto usa `https://devs.seismik.org/v1/oauth/google/callback` como URI de
redirección. Google exige que el **dominio privado superior** —`seismik.org`—
figure como dominio autorizado, y para autorizarlo hay que haberlo verificado.
Verificar sólo `devs.seismik.org` no basta.

## Opción A — Registro DNS TXT (recomendada)

Es la única que cubre `seismik.org` y todos sus subdominios de una vez, incluidos
los que se añadan después, y no obliga a volver a desplegar la web.

1. Entra en [Search Console](https://search.google.com/search-console) con **la
   misma cuenta de Google que es dueña del proyecto de OAuth**. Si no es la
   misma, la verificación no sirve.
2. Añadir propiedad → **Dominio** → `seismik.org`.
3. Google entrega un registro TXT del tipo
   `google-site-verification=XXXXXXXXXXXXXXXXXXXXXXXX`.
4. Crea ese TXT en el DNS del registrador, en la raíz del dominio (`@`).
5. Espera a que propague y pulsa *Verificar*. Suele tardar minutos, a veces
   horas.

## Opción B — Archivo HTML en la raíz

Sirve si no hay acceso al DNS. Verifica sólo `https://seismik.org`.

1. Search Console → Añadir propiedad → **Prefijo de URL** → `https://seismik.org`.
2. Descarga el archivo `googleXXXXXXXX.html` que ofrece Google.
3. Colócalo en `web/` de este repositorio. Caddy sirve ese directorio como raíz
   (`root * /srv`), así que quedará en `https://seismik.org/googleXXXXXXXX.html`.
4. Despliega la web y pulsa *Verificar*.

No borres el archivo después: Google revisa la propiedad periódicamente y la
retira si desaparece.

## Opción C — Etiqueta meta

Equivalente a la opción B en alcance y también exige desplegar. El `<head>` de
`web/index.html` lleva un comentario que marca dónde pegar la etiqueta que
entrega Google:

```html
<meta name="google-site-verification" content="TOKEN_DE_GOOGLE">
```

## Después de verificar

1. En la consola de Google Cloud → *APIs y servicios* → *Pantalla de
   consentimiento de OAuth*, comprueba que `seismik.org` aparece en **Dominios
   autorizados**.
2. Vuelve al diálogo de verificación de marca y elige **«Corregí los
   problemas»** para pedir una nueva revisión. La otra opción —«Considero que
   los problemas detectados son incorrectos»— sólo tiene sentido si crees que
   Google se equivocó, y aquí no es el caso: el dominio efectivamente no estaba
   verificado.

## Lo que la web ya cumple

Estos son el resto de requisitos que Google revisa en la misma verificación, y
que el sitio ya satisface. Conviene no romperlos al editar las páginas;
`tests/test_web_assets.py` los comprueba en cada ejecución de la suite:

| Requisito | Dónde |
|---|---|
| Página principal pública que explica qué hace el producto | `web/index.html` |
| Enlace visible a la política de privacidad | Cabecera y pie de `index.html` |
| Enlace visible a los términos de servicio | Cabecera y pie de `index.html` |
| Privacidad y términos en el mismo dominio verificado | `/terms-of-privacy`, `/terms-of-service` |
| Identidad coherente: nombre y logotipo | Cabecera y juego de iconos |

El logotipo que se sube a la pantalla de consentimiento debe ser el mismo que
usa el sitio: `web/assets/seismik_logo.png`.
