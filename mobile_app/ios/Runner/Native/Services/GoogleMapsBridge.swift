import Foundation
import GoogleMaps

/// Puente de control para la inicialización y uso seguro de Google Maps SDK en iOS.
/// Previene crashes por excepciones no capturables cuando la clave de API no está presente o falla la inicialización.
public enum GoogleMapsBridge {
    public private(set) static var isAvailable: Bool = false

    /// Inicializa los servicios de Google Maps con la clave provista.
    public static func initialize(with apiKey: String) {
        let trimmed = apiKey.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, !trimmed.hasPrefix("$(") else {
            isAvailable = false
            NSLog("[Seismik] Clave de Google Maps vacia o no configurada; el SDK permanecera inactivo.")
            return
        }
        let ok = GMSServices.provideAPIKey(trimmed)
        isAvailable = ok
        if ok {
            NSLog("[Seismik] Google Maps SDK inicializado con exito.")
        } else {
            NSLog("[Seismik] GMSServices.provideAPIKey no pudo inicializar el SDK.")
        }
    }
}
