import Foundation
import CoreLocation

/// Modelo de datos para un evento sísmico detectado o reportado.
public struct SeismicEvent: Identifiable, Codable, Hashable {
    public let id: String
    public let place: String?
    public let magnitude: Double?
    public let depthKm: Double?
    public let latitude: Double?
    public let longitude: Double?
    public let detectedAt: Date?
    public let sourceId: String?
    public let agency: String?
    public let isPreliminary: Bool
    public let intensityMmi: Int?
    public let tsunamiWarning: Bool

    enum CodingKeys: String, CodingKey {
        case id
        case place
        case magnitude
        case depthKm = "depth_km"
        case latitude
        case longitude
        case detectedAt = "detected_at"
        case sourceId = "source_id"
        case agency
        case isPreliminary = "is_preliminary"
        case intensityMmi = "intensity_mmi"
        case tsunamiWarning = "tsunami_warning"
    }

    public init(
        id: String,
        place: String?,
        magnitude: Double?,
        depthKm: Double?,
        latitude: Double?,
        longitude: Double?,
        detectedAt: Date?,
        sourceId: String? = nil,
        agency: String? = nil,
        isPreliminary: Bool = false,
        intensityMmi: Int? = nil,
        tsunamiWarning: Bool = false
    ) {
        self.id = id
        self.place = place
        self.magnitude = magnitude
        self.depthKm = depthKm
        self.latitude = latitude
        self.longitude = longitude
        self.detectedAt = detectedAt
        self.sourceId = sourceId
        self.agency = agency
        self.isPreliminary = isPreliminary
        self.intensityMmi = intensityMmi
        self.tsunamiWarning = tsunamiWarning
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        place = try container.decodeIfPresent(String.self, forKey: .place)
        magnitude = try container.decodeIfPresent(Double.self, forKey: .magnitude)
        depthKm = try container.decodeIfPresent(Double.self, forKey: .depthKm)
        latitude = try container.decodeIfPresent(Double.self, forKey: .latitude)
        longitude = try container.decodeIfPresent(Double.self, forKey: .longitude)
        sourceId = try container.decodeIfPresent(String.self, forKey: .sourceId)
        agency = try container.decodeIfPresent(String.self, forKey: .agency)
        isPreliminary = try container.decodeIfPresent(Bool.self, forKey: .isPreliminary) ?? false
        intensityMmi = try container.decodeIfPresent(Int.self, forKey: .intensityMmi)
        tsunamiWarning = try container.decodeIfPresent(Bool.self, forKey: .tsunamiWarning) ?? false

        // Manejo flexible de fechas ISO8601 o timestamps
        if let dateString = try? container.decodeIfPresent(String.self, forKey: .detectedAt) {
            detectedAt = ISO8601DateFormatter().date(from: dateString)
        } else if let timestamp = try? container.decodeIfPresent(Double.self, forKey: .detectedAt) {
            detectedAt = Date(timeIntervalSince1970: timestamp)
        } else {
            detectedAt = nil
        }
    }

    public var coordinate: CLLocationCoordinate2D? {
        guard let lat = latitude, let lon = longitude else { return nil }
        return CLLocationCoordinate2D(latitude: lat, longitude: lon)
    }

    public var agencyDisplayName: String {
        if isPreliminary { return "SeedLink · preliminar" }
        if let src = sourceId {
            switch src {
            case "sgc_colombia": return "SGC · Colombia"
            case "usgs_global": return "USGS · Global"
            case "igp_peru": return "IGP · Perú"
            case "ingv_italy": return "INGV · Italia"
            case "geonet_new_zealand": return "GeoNet · N. Zelanda"
            case "bmkg_indonesia": return "BMKG · Indonesia"
            case "jma_japan": return "JMA · Japón"
            default: return src
            }
        }
        return agency ?? "Oficial"
    }

    public var relativeTimeFormatted: String {
        guard let date = detectedAt else { return "Reciente" }
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .full
        formatter.locale = Locale(identifier: "es_CO")
        return formatter.localizedString(for: date, relativeTo: Date())
    }

    public var formattedDateTime: String {
        guard let date = detectedAt else { return "Fecha desconocida" }
        let formatter = DateFormatter()
        formatter.dateStyle = .medium
        formatter.timeStyle = .medium
        formatter.locale = Locale(identifier: "es_CO")
        return formatter.string(from: date)
    }
}
