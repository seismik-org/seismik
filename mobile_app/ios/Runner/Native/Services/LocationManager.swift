import Foundation
import CoreLocation
import Combine

/// Gestor nativo de geolocalización utilizando CoreLocation.
public final class LocationManager: NSObject, ObservableObject, CLLocationManagerDelegate {
    public static let shared = LocationManager()

    private let manager = CLLocationManager()

    @Published public var userCoordinate: CLLocationCoordinate2D?
    @Published public var authorizationStatus: CLAuthorizationStatus = .notDetermined

    /// Coordenada actual del usuario utilizando la última posición reportada o en caché.
    public var currentCoordinate: CLLocationCoordinate2D? {
        userCoordinate ?? manager.location?.coordinate
    }

    public override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyKilometer
        self.authorizationStatus = manager.authorizationStatus
        if authorizationStatus == .authorizedWhenInUse || authorizationStatus == .authorizedAlways {
            if let cached = manager.location?.coordinate {
                self.userCoordinate = cached
            }
            manager.startUpdatingLocation()
        }
    }

    /// Solicita permiso de ubicación mientras se usa la app o refresca si ya está concedido.
    public func requestPermission() {
        if manager.authorizationStatus == .notDetermined {
            manager.requestWhenInUseAuthorization()
        } else if manager.authorizationStatus == .authorizedWhenInUse || manager.authorizationStatus == .authorizedAlways {
            if let cached = manager.location?.coordinate {
                self.userCoordinate = cached
            }
            manager.startUpdatingLocation()
        }
    }

    /// Inicia el seguimiento ligero de la posición del usuario.
    public func startUpdating() {
        if let cached = manager.location?.coordinate {
            self.userCoordinate = cached
        }
        manager.startUpdatingLocation()
    }

    /// Detiene las actualizaciones de ubicación para conservar batería.
    public func stopUpdating() {
        manager.stopUpdatingLocation()
    }

    // MARK: - CLLocationManagerDelegate

    public func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        DispatchQueue.main.async {
            self.authorizationStatus = manager.authorizationStatus
            if manager.authorizationStatus == .authorizedWhenInUse || manager.authorizationStatus == .authorizedAlways {
                manager.startUpdatingLocation()
            }
        }
    }

    public func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let latest = locations.last else { return }
        DispatchQueue.main.async {
            self.userCoordinate = latest.coordinate
        }
    }

    public func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        // Fallo silencioso con respaldo de última ubicación conocida
    }

    /// Calcula la distancia en kilómetros entre el usuario y un sismo.
    public func distance(to coordinate: CLLocationCoordinate2D) -> Double? {
        guard let user = userCoordinate else { return nil }
        let userLoc = CLLocation(latitude: user.latitude, longitude: user.longitude)
        let targetLoc = CLLocation(latitude: coordinate.latitude, longitude: coordinate.longitude)
        return userLoc.distance(from: targetLoc) / 1000.0
    }
}
