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

/// Mapa que la app dibuja por dentro. La preferencia se guarda como texto en
/// `seismik.map_provider`.
public enum MapProviderChoice: String, CaseIterable {
    case apple
    case google

    public var label: String {
        switch self {
        case .apple: return "Apple Maps"
        case .google: return "Google Maps"
        }
    }

    /// Versiones anteriores guardaron "system" y "osm". Ninguno de los dos
    /// dibujaba nada distinto, así que ambos vuelven a Apple Maps.
    public static func stored(_ raw: String) -> MapProviderChoice {
        MapProviderChoice(rawValue: raw) ?? .apple
    }

    /// Sin clave del SDK, Google Maps sale como una cuadrícula gris. Antes de
    /// mostrar eso, la app dibuja Apple Maps.
    public static func resolved(stored raw: String, googleIsReady: Bool) -> MapProviderChoice {
        let choice = stored(raw)
        return choice == .google && !googleIsReady ? .apple : choice
    }
}
