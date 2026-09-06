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

    public init(
        network: String = "CM",
        stationCode: String,
        latitude: Double,
        longitude: Double,
        elevation: Double? = nil
    ) {
        self.network = network
        self.stationCode = stationCode
        self.latitude = latitude
        self.longitude = longitude
        self.elevation = elevation
    }

    enum CodingKeys: String, CodingKey {
        case network
        case stationId = "station_id"
        case id
        case latitude
        case longitude
        case elevation
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.network = (try? container.decode(String.self, forKey: .network)) ?? "CM"
        if let sId = try? container.decode(String.self, forKey: .stationId) {
            self.stationCode = sId
        } else if let idVal = try? container.decode(String.self, forKey: .id) {
            self.stationCode = idVal
        } else {
            self.stationCode = "STA"
        }
        self.latitude = try container.decode(Double.self, forKey: .latitude)
        self.longitude = try container.decode(Double.self, forKey: .longitude)
        self.elevation = try? container.decodeIfPresent(Double.self, forKey: .elevation)
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(network, forKey: .network)
        try container.encode(stationCode, forKey: .stationId)
        try container.encode(latitude, forKey: .latitude)
        try container.encode(longitude, forKey: .longitude)
        try container.encodeIfPresent(elevation, forKey: .elevation)
    }

    public var coordinate: CLLocationCoordinate2D {
        CLLocationCoordinate2D(latitude: latitude, longitude: longitude)
    }
}

