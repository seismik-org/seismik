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
        case eventId = "event_id"
        case place
        case magnitude
        case depthKm = "depth_km"
        case latitude
        case estimatedLatitude = "estimated_latitude"
        case longitude
        case estimatedLongitude = "estimated_longitude"
        case detectedAt = "detected_at"
        case originTime = "origin_time"
        case sourceId = "source_id"
        case agency
        case isPreliminary = "is_preliminary"
        case preliminary
        case intensityMmi = "intensity_mmi"
        case tsunamiWarning = "tsunami_warning"
        case tsunami
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
        if let idVal = try? container.decode(String.self, forKey: .id) {
            id = idVal
        } else if let eId = try? container.decode(String.self, forKey: .eventId) {
            id = eId
        } else {
            id = UUID().uuidString
        }
        place = try container.decodeIfPresent(String.self, forKey: .place)
        magnitude = try container.decodeIfPresent(Double.self, forKey: .magnitude)
        depthKm = try container.decodeIfPresent(Double.self, forKey: .depthKm)
        latitude = (try? container.decodeIfPresent(Double.self, forKey: .latitude))
            ?? (try? container.decodeIfPresent(Double.self, forKey: .estimatedLatitude))
        longitude = (try? container.decodeIfPresent(Double.self, forKey: .longitude))
            ?? (try? container.decodeIfPresent(Double.self, forKey: .estimatedLongitude))
        sourceId = try container.decodeIfPresent(String.self, forKey: .sourceId)
        agency = try container.decodeIfPresent(String.self, forKey: .agency)
        
        let prelimBool = (try? container.decodeIfPresent(Bool.self, forKey: .isPreliminary))
            ?? (try? container.decodeIfPresent(Bool.self, forKey: .preliminary))
            ?? false
        isPreliminary = prelimBool
        
        intensityMmi = try container.decodeIfPresent(Int.self, forKey: .intensityMmi)
        
        let tsuBool = (try? container.decodeIfPresent(Bool.self, forKey: .tsunamiWarning))
            ?? (try? container.decodeIfPresent(Bool.self, forKey: .tsunami))
            ?? false
        tsunamiWarning = tsuBool

        // Manejo flexible de fechas ISO8601 o timestamps
        if let dateString = (try? container.decodeIfPresent(String.self, forKey: .detectedAt))
            ?? (try? container.decodeIfPresent(String.self, forKey: .originTime)) {
            let formatter = ISO8601DateFormatter()
            formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            if let parsed = formatter.date(from: dateString) {
                detectedAt = parsed
            } else {
                detectedAt = ISO8601DateFormatter().date(from: dateString)
            }
        } else if let timestamp = try? container.decodeIfPresent(Double.self, forKey: .detectedAt) {
            detectedAt = Date(timeIntervalSince1970: timestamp)
        } else {
            detectedAt = nil
        }
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(id, forKey: .id)
        try container.encodeIfPresent(place, forKey: .place)
        try container.encodeIfPresent(magnitude, forKey: .magnitude)
        try container.encodeIfPresent(depthKm, forKey: .depthKm)
        try container.encodeIfPresent(latitude, forKey: .latitude)
        try container.encodeIfPresent(longitude, forKey: .longitude)
        if let date = detectedAt {
            try container.encode(ISO8601DateFormatter().string(from: date), forKey: .detectedAt)
        }
        try container.encodeIfPresent(sourceId, forKey: .sourceId)
        try container.encodeIfPresent(agency, forKey: .agency)
        try container.encode(isPreliminary, forKey: .isPreliminary)
        try container.encodeIfPresent(intensityMmi, forKey: .intensityMmi)
        try container.encode(tsunamiWarning, forKey: .tsunamiWarning)
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

extension SeismicEvent {
    public static let sampleEvents: [SeismicEvent] = [
        SeismicEvent(
            id: "sgc_colombia:2026-09-06-001",
            place: "59 km al SO de Los Santos, Santander",
            magnitude: 4.1,
            depthKm: 145.0,
            latitude: 6.78,
            longitude: -73.12,
            detectedAt: Date().addingTimeInterval(-7200),
            sourceId: "sgc_colombia",
            agency: "SGC · Colombia",
            isPreliminary: false,
            intensityMmi: 4,
            tsunamiWarning: false
        ),
        SeismicEvent(
            id: "sgc_colombia:2026-09-06-002",
            place: "Mesetas, Meta",
            magnitude: 3.5,
            depthKm: 12.0,
            latitude: 3.38,
            longitude: -74.04,
            detectedAt: Date().addingTimeInterval(-18000),
            sourceId: "sgc_colombia",
            agency: "SGC · Colombia",
            isPreliminary: false,
            intensityMmi: 3,
            tsunamiWarning: false
        ),
        SeismicEvent(
            id: "usgs_global:2026-09-06-003",
            place: "Costa Rica - Frontera con Panamá",
            magnitude: 5.2,
            depthKm: 25.0,
            latitude: 8.24,
            longitude: -82.90,
            detectedAt: Date().addingTimeInterval(-36000),
            sourceId: "usgs_global",
            agency: "USGS · Global",
            isPreliminary: false,
            intensityMmi: 5,
            tsunamiWarning: false
        ),
        SeismicEvent(
            id: "sgc_colombia:2026-09-06-004",
            place: "Zapatoca, Santander",
            magnitude: 2.8,
            depthKm: 130.0,
            latitude: 6.82,
            longitude: -73.27,
            detectedAt: Date().addingTimeInterval(-54000),
            sourceId: "sgc_colombia",
            agency: "SGC · Colombia",
            isPreliminary: false,
            intensityMmi: 2,
            tsunamiWarning: false
        ),
        SeismicEvent(
            id: "sgc_colombia:2026-09-06-005",
            place: "El Calvario, Meta",
            magnitude: 3.1,
            depthKm: 10.0,
            latitude: 4.45,
            longitude: -73.71,
            detectedAt: Date().addingTimeInterval(-86400),
            sourceId: "sgc_colombia",
            agency: "SGC · Colombia",
            isPreliminary: false,
            intensityMmi: 3,
            tsunamiWarning: false
        )
    ]
}

