import Foundation

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
