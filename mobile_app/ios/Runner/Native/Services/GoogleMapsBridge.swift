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

/// App con la que se abre el epicentro de un sismo fuera de Seismik. El mapa
/// que la app dibuja por dentro es siempre Apple Maps: el SDK de Google se
/// probó en el build 51 y se quitó porque no llegaba a cargar mosaicos.
/// La preferencia se guarda como texto en `seismik.map_provider`.
public enum MapProviderChoice: String, CaseIterable {
    case apple
    case google

    public var label: String {
        switch self {
        case .apple: return "Apple Maps"
        case .google: return "Google Maps"
        }
    }

    /// Versiones anteriores guardaron "system" y "osm"; ambos vuelven a Apple.
    public static func stored(_ raw: String) -> MapProviderChoice {
        MapProviderChoice(rawValue: raw) ?? .apple
    }
}
