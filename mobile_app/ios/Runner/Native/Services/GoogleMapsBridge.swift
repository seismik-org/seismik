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

/// Vigilante del mapa de Google.
///
/// El proveedor se guarda en el teléfono, así que si dibujar ese mapa tumba la
/// app, la app vuelve a arrancar, vuelve a dibujarlo y vuelve a caerse: queda
/// sin abrir y sin forma de cambiar el ajuste desde dentro. Antes de crear el
/// mapa se deja una marca en disco y se borra cuatro segundos después; si al
/// arrancar la marca sigue ahí, es que el intento anterior no sobrevivió y la
/// app vuelve a Apple Maps.
public enum GoogleMapGuard {
    /// Segundos que el mapa debe aguantar en pantalla para darlo por bueno.
    private static let survivalSeconds: TimeInterval = 4

    /// La marca vive en Caches: si el sistema la borra, el vigilante sólo
    /// olvida un intento, que es el lado seguro del error.
    public static var markerURL: URL = {
        let caches = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)
        let folder = caches.first ?? URL(fileURLWithPath: NSTemporaryDirectory())
        return folder.appendingPathComponent("seismik-google-map-attempt")
    }()

    public static func isMarked(at url: URL = GoogleMapGuard.markerURL) -> Bool {
        FileManager.default.fileExists(atPath: url.path)
    }

    public static func mark(at url: URL = GoogleMapGuard.markerURL) {
        FileManager.default.createFile(atPath: url.path, contents: Data())
    }

    public static func clear(at url: URL = GoogleMapGuard.markerURL) {
        try? FileManager.default.removeItem(at: url)
    }

    /// Clave que recuerda que hubo que volver a Apple Maps, para poder
    /// explicarlo en Configuración en lugar de cambiar el ajuste en silencio.
    public static let revertedKey = "seismik.map_provider.google_reverted"

    /// Proveedor con el que se puede arrancar sin riesgo. Devuelve Apple si el
    /// intento anterior se quedó a medias, y limpia la marca para que el
    /// siguiente intento parta de cero.
    public static func safeProvider(
        stored raw: String,
        at url: URL = GoogleMapGuard.markerURL,
        defaults: UserDefaults = .standard
    ) -> String {
        guard isMarked(at: url) else { return MapProviderChoice.stored(raw).rawValue }
        clear(at: url)
        defaults.set(true, forKey: revertedKey)
        return MapProviderChoice.apple.rawValue
    }

    /// Crea el mapa de Google dejando la marca puesta mientras se dibuja.
    public static func makeMapView(camera: GMSCameraPosition) -> GMSMapView {
        mark()
        let mapView = GMSMapView(frame: .zero, camera: camera)
        DispatchQueue.main.asyncAfter(deadline: .now() + survivalSeconds) {
            clear()
        }
        return mapView
    }
}
