import Foundation
import GoogleMaps

/// Puente de control para la inicialización y uso seguro de Google Maps SDK en iOS.
/// Previene crashes por excepciones no capturables cuando la clave de API no está presente o falla la inicialización.
public enum GoogleMapsBridge {
    public private(set) static var isAvailable: Bool = false

    /// Inicializa los servicios de Google Maps con la clave provista.
    public static func initialize(with apiKey: String) {
        guard !apiKey.isEmpty, !apiKey.hasPrefix("$(") else {
            NSLog("[Seismik] Clave de Google Maps vacia o invalida; el SDK permanecera inactivo.")
            return
        }
        GMSServices.provideAPIKey(apiKey)
        isAvailable = true
        NSLog("[Seismik] Google Maps SDK inicializado con exito.")
    }
}
