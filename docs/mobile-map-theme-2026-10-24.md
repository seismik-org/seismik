# Mapas y textos del sistema — 2026-10-24

Base: versión móvil 1.0.0+68, rama `fix/mobile-map-theme-20261024`.
Tras la solicitud de publicar iOS se incrementó el build a 1.0.0+69 y se prepara
el workflow habitual de GitHub con subida a TestFlight y Critical Alerts.

- Android/Flutter: historial, detalle y familia aplican un estilo JSON local
  oscuro según `Theme.of(context).brightness`. Al volver a claro se retira el
  estilo. No requiere una descarga, otro mapa ni cambios de credenciales.
  Se conserva la decisión explícita de tema de la persona; con «Sistema» sigue
  los cambios claro/oscuro del celular en caliente. `colorScheme` complementa
  los mapas web; el estilo JSON es el que cubre los renderizadores nativos.
- iOS nativo: los puentes MKMapView de historial y detalle leen el colorScheme
  de SwiftUI al crear y actualizar la vista. El mapa familiar de SwiftUI ya
  hereda ese entorno. No cambia la ubicación, los marcadores o los perímetros.
- Android: pestaña corta «Ajustes», tooltip y título de pantalla
  «Configuración». Etiquetas en una línea con elipsis cuando sea necesario,
  sin desactivar el escalado de accesibilidad ni cortar palabras en dos líneas.
- Opción «Usa el color del sistema» y explicación «Usa los colores que elegiste
  para tu celular». Se conservan preferencias guardadas y colores dinámicos.

## Verificación

Análisis de Dart sin incidencias. Suite completa de Flutter: 181 pruebas
aprobadas, incluidas cinco nuevas de JSON, cambios de brillo y navegación a
320 px con escalas de texto 1, 1.5 y 2; el botón Ajustes sigue abriendo índice 4.
No se ha comprobado el mapa real en un teléfono en esta tarea.

## Entrega posterior solicitada

- GitHub Actions iOS `40120171919`: SUCCESS, incluido IPA firmado con Xcode,
  verificación de Critical Alerts y subida a TestFlight. Disponibilidad final
  del grupo de TestFlight no comprobada en esta entrega de Android.
- Android 1.0.0 (69): publicado mediante Play Console en la pista interna
  existente, el 24 de octubre a las 14:39 America/Bogota. La interfaz confirma
  «Disponible para verificadores internos». No cambian los verificadores ni
  la compatibilidad de dispositivos. No es un lanzamiento público a producción.
- Se conservan certificado de subida y configuración de Firebase y Maps.
- AAB SHA-256:
  `3B7C611ACE268F25743216B44DC4286B1526BB8617A5B2145BA90F13E83482CE`.
- Evidencia local: `work/releases/build69/RELEASE.md`, AAB y
  `play-internal-69.png`. No se publican binarios ni credenciales en Git.
