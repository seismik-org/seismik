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
No se ha comprobado el mapa real en un teléfono en esta tarea ni compilado el
código nativo Swift con Xcode (equipo Windows). Pendiente para la próxima
compilación/publicación en Android y TestFlight.
