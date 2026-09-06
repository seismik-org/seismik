import Foundation
import CoreLocation

/// Estación sismológica que integra la red de monitoreo.
public struct SeismicStation: Identifiable, Codable, Hashable {
    public var id: String { "\(network).\(stationCode)" }
    public let network: String
    public let stationCode: String
    public let latitude: Double
    public let longitude: Double
    public let elevation: Double?

    enum CodingKeys: String, CodingKey {
        case network
        case stationCode = "id"
        case latitude
        case longitude
        case elevation
    }

    public var coordinate: CLLocationCoordinate2D {
        CLLocationCoordinate2D(latitude: latitude, longitude: longitude)
    }
}
