# Retirada de la clave de Maps de iOS — 10 de octubre de 2026

El mapa interno de iOS usa Apple MapKit. Se retiró la clave dedicada
«Seismik iOS Maps» de Google Cloud y su secreto de GitHub Actions. Se eliminó
la inicialización residual de Google Maps del arranque, Info.plist y xcconfig,
sin retirar Firebase, App Check, APNs ni Critical Alerts.

La opción de abrir un epicentro en la aplicación externa Google Maps permanece:
utiliza una URL y no requiere esta clave. Las claves de Android y de la web no
se modificaron. Los plugins Flutter compartidos se conservan para Android;
esta actualización no pretende eliminar todas las dependencias transitivas de Maps.

Las versiones antiguas que todavía dibujaban mapas con el SDK de Google podrían
perderlos al retirarse la clave. Las versiones actuales con MapKit no dependen
de ella. El cambio en GitHub no equivale a publicar un nuevo build en TestFlight.
