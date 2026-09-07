import Foundation
import CoreLocation

/// Registro de disparo de estación sismológica para coincidencia multiestación.
public struct StationTrigger: Identifiable, Codable, Hashable {
    public var id: String { stationId }
    public let stationId: String
    public let providerId: String
    public let countryCode: String?
    public let triggerTime: Date?
    public let staLtaRatio: Double
    public let peakAmplitudeCounts: Double?

    enum CodingKeys: String, CodingKey {
        case stationId = "station_id"
        case providerId = "provider_id"
        case countryCode = "country_code"
        case triggerTime = "trigger_time"
        case staLtaRatio = "sta_lta_ratio"
        case peakAmplitudeCounts = "peak_amplitude_counts"
    }

    public init(
        stationId: String,
        providerId: String,
        countryCode: String? = nil,
        triggerTime: Date? = nil,
        staLtaRatio: Double,
        peakAmplitudeCounts: Double? = nil
    ) {
        self.stationId = stationId
        self.providerId = providerId
        self.countryCode = countryCode
        self.triggerTime = triggerTime
        self.staLtaRatio = staLtaRatio
        self.peakAmplitudeCounts = peakAmplitudeCounts
    }

    public var triggerTimeFormatted: String {
        guard let date = triggerTime else { return "—" }
        let formatter = DateFormatter()
        formatter.dateFormat = "HH:mm:ss 'UTC'"
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        return formatter.string(from: date)
    }

    public var peakAmplitudeFormatted: String {
        guard let peak = peakAmplitudeCounts else { return "—" }
        return String(format: "Pico %.1f c", peak)
    }
}


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
    public let officialEventId: String?
    public let agency: String?
    public let isPreliminary: Bool
    public let intensityMmi: Int?
    public let tsunamiWarning: Bool
    public let magnitudeType: String?
    public let reviewStatus: String?
    public let stationCount: Int?
    public let coincidenceWindowSeconds: Double?
    public let waveStrengthIndex: Double?
    public let officialUrl: String?
    public let zoneId: String?
    public let countryCodes: [String]
    public let algorithm: String?
    public let magnitudeEstimateStatus: String?
    public let stations: [StationTrigger]

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
        case emittedAt = "emitted_at"
        case sourceId = "source_id"
        case officialEventId = "official_event_id"
        case agency
        case isPreliminary = "is_preliminary"
        case preliminary
        case intensityMmi = "intensity_mmi"
        case tsunamiWarning = "tsunami_warning"
        case tsunami
        case magnitudeType = "magnitude_type"
        case reviewStatus = "review_status"
        case stationCount = "station_count"
        case coincidenceWindowSeconds = "coincidence_window_seconds"
        case waveStrengthIndex = "wave_strength_index"
        case officialUrl = "official_url"
        case zoneId = "zone_id"
        case countryCodes = "country_codes"
        case algorithm
        case magnitudeEstimateStatus = "magnitude_estimate_status"
        case stations
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
        officialEventId: String? = nil,
        agency: String? = nil,
        isPreliminary: Bool = false,
        intensityMmi: Int? = nil,
        tsunamiWarning: Bool = false,
        magnitudeType: String? = nil,
        reviewStatus: String? = nil,
        stationCount: Int? = nil,
        coincidenceWindowSeconds: Double? = nil,
        waveStrengthIndex: Double? = nil,
        officialUrl: String? = nil,
        zoneId: String? = nil,
        countryCodes: [String] = [],
        algorithm: String? = nil,
        magnitudeEstimateStatus: String? = nil,
        stations: [StationTrigger] = []
    ) {
        self.id = id
        self.place = place
        self.magnitude = magnitude
        self.depthKm = depthKm
        self.latitude = latitude
        self.longitude = longitude
        self.detectedAt = detectedAt
        self.sourceId = sourceId
        self.officialEventId = officialEventId
        self.agency = agency
        self.isPreliminary = isPreliminary
        self.intensityMmi = intensityMmi
        self.tsunamiWarning = tsunamiWarning
        self.magnitudeType = magnitudeType
        self.reviewStatus = reviewStatus
        self.stationCount = stationCount
        self.coincidenceWindowSeconds = coincidenceWindowSeconds
        self.waveStrengthIndex = waveStrengthIndex
        self.officialUrl = officialUrl
        self.zoneId = zoneId
        self.countryCodes = countryCodes
        self.algorithm = algorithm
        self.magnitudeEstimateStatus = magnitudeEstimateStatus
        self.stations = stations
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
        officialEventId = try container.decodeIfPresent(String.self, forKey: .officialEventId)
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

        magnitudeType = try container.decodeIfPresent(String.self, forKey: .magnitudeType)
        reviewStatus = try container.decodeIfPresent(String.self, forKey: .reviewStatus)
        stationCount = try container.decodeIfPresent(Int.self, forKey: .stationCount)
        coincidenceWindowSeconds = try container.decodeIfPresent(Double.self, forKey: .coincidenceWindowSeconds)
        waveStrengthIndex = try container.decodeIfPresent(Double.self, forKey: .waveStrengthIndex)
        officialUrl = try container.decodeIfPresent(String.self, forKey: .officialUrl)
        zoneId = try container.decodeIfPresent(String.self, forKey: .zoneId)
        countryCodes = (try? container.decodeIfPresent([String].self, forKey: .countryCodes)) ?? []
        algorithm = try container.decodeIfPresent(String.self, forKey: .algorithm)
        magnitudeEstimateStatus = try container.decodeIfPresent(String.self, forKey: .magnitudeEstimateStatus)
        stations = (try? container.decodeIfPresent([StationTrigger].self, forKey: .stations)) ?? []

        // Manejo flexible de fechas ISO8601 o timestamps
        // `/v1/alerts/recent` fecha cada aviso con `emitted_at`; el historial usa
        // `detected_at` u `origin_time`. Sin esta tercera clave, las alertas
        // recuperadas sin conexión llegaban sin hora y se ordenaban al final.
        if let dateString = (try? container.decodeIfPresent(String.self, forKey: .detectedAt))
            ?? (try? container.decodeIfPresent(String.self, forKey: .originTime))
            ?? (try? container.decodeIfPresent(String.self, forKey: .emittedAt)) {
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
        try container.encodeIfPresent(officialEventId, forKey: .officialEventId)
        try container.encodeIfPresent(agency, forKey: .agency)
        try container.encode(isPreliminary, forKey: .isPreliminary)
        try container.encodeIfPresent(intensityMmi, forKey: .intensityMmi)
        try container.encode(tsunamiWarning, forKey: .tsunamiWarning)
        try container.encodeIfPresent(magnitudeType, forKey: .magnitudeType)
        try container.encodeIfPresent(reviewStatus, forKey: .reviewStatus)
        try container.encodeIfPresent(stationCount, forKey: .stationCount)
        try container.encodeIfPresent(coincidenceWindowSeconds, forKey: .coincidenceWindowSeconds)
        try container.encodeIfPresent(waveStrengthIndex, forKey: .waveStrengthIndex)
        try container.encodeIfPresent(officialUrl, forKey: .officialUrl)
        try container.encodeIfPresent(zoneId, forKey: .zoneId)
        try container.encode(countryCodes, forKey: .countryCodes)
        try container.encodeIfPresent(algorithm, forKey: .algorithm)
        try container.encodeIfPresent(magnitudeEstimateStatus, forKey: .magnitudeEstimateStatus)
        try container.encode(stations, forKey: .stations)
    }

    public var utcTimeFormatted: String {
        guard let date = detectedAt else { return "—" }
        let formatter = DateFormatter()
        formatter.dateFormat = "HH:mm:ss"
        formatter.timeZone = TimeZone(identifier: "UTC")
        return formatter.string(from: date)
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

    /// APNs serializa los campos personalizados como cadenas. Este inicializador
    /// normaliza esos valores sin depender del decoder JSON del historial.
    public init?(notificationUserInfo userInfo: [AnyHashable: Any]) {
        func text(_ key: String) -> String? {
            guard let value = userInfo[key] else { return nil }
            let result = String(describing: value)
            return result.isEmpty ? nil : result
        }
        func number(_ key: String) -> Double? {
            guard let value = text(key), !value.isEmpty else { return nil }
            return Double(value)
        }

        guard let eventId = text("event_id") else { return nil }
        let type = text("type") ?? ""
        let dateText = text("detected_at") ?? text("origin_time")
        let parsedDate = dateText.flatMap { value -> Date? in
            let fractional = ISO8601DateFormatter()
            fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            return fractional.date(from: value) ?? ISO8601DateFormatter().date(from: value)
        }
        self.init(
            id: eventId,
            place: text("place") ?? text("zone_id").map { "Zona \($0)" },
            magnitude: number("magnitude"),
            depthKm: number("depth_km"),
            latitude: number("latitude") ?? number("estimated_latitude"),
            longitude: number("longitude") ?? number("estimated_longitude"),
            detectedAt: parsedDate ?? Date(),
            sourceId: type == "earthquake_candidate" ? "seismik_seedlink_preliminary" : nil,
            agency: text("agency") ?? (type == "earthquake_candidate" ? "Seismik / SeedLink" : nil),
            isPreliminary: type == "earthquake_candidate",
            intensityMmi: nil,
            tsunamiWarning: false,
            officialUrl: text("official_url"),
            zoneId: text("zone_id")
        )
    }
}

extension SeismicEvent {
    public static let sampleEvents: [SeismicEvent] = [
        SeismicEvent(
            id: "usgs:ak026bldz704",
            place: "48 km SSE of Nelchina, Alaska",
            magnitude: 2.6,
            depthKm: 13.9,
            latitude: 61.59,
            longitude: -146.59,
            detectedAt: Date().addingTimeInterval(-2400),
            sourceId: "usgs_global",
            agency: "United States Geological Survey (USGS)",
            isPreliminary: false,
            intensityMmi: 2,
            tsunamiWarning: false,
            magnitudeType: "Mml",
            reviewStatus: "automatic",
            officialUrl: "https://earthquake.usgs.gov"
        ),
        SeismicEvent(
            id: "seedlink:20260906-co-01",
            place: "Zona técnica CO",
            magnitude: nil,
            depthKm: nil,
            latitude: 10.45,
            longitude: -73.25,
            detectedAt: Date().addingTimeInterval(-900),
            sourceId: "seismik_seedlink_preliminary",
            agency: "Seismik / SeedLink",
            isPreliminary: true,
            intensityMmi: nil,
            tsunamiWarning: false,
            magnitudeType: nil,
            reviewStatus: "preliminar - sin revisión humana",
            stationCount: 3,
            coincidenceWindowSeconds: 10.0,
            waveStrengthIndex: 0.94,
            zoneId: "CO",
            countryCodes: ["CO"],
            algorithm: "STA/LTA con coincidencia multiestación",
            magnitudeEstimateStatus: "pending_station_calibration",
            stations: [
                StationTrigger(
                    stationId: "CM.ARGC",
                    providerId: "earthscope_colombia",
                    countryCode: "CC",
                    triggerTime: Date().addingTimeInterval(-915),
                    staLtaRatio: 7.9,
                    peakAmplitudeCounts: 499.4
                ),
                StationTrigger(
                    stationId: "CM.OCA",
                    providerId: "earthscope_colombia",
                    countryCode: "CC",
                    triggerTime: Date().addingTimeInterval(-908),
                    staLtaRatio: 7.9,
                    peakAmplitudeCounts: 17245.7
                ),
                StationTrigger(
                    stationId: "CM.CRJC",
                    providerId: "earthscope_colombia",
                    countryCode: "CC",
                    triggerTime: Date().addingTimeInterval(-901),
                    staLtaRatio: 16.8,
                    peakAmplitudeCounts: 677.0
                )
            ]
        ),
        SeismicEvent(
            id: "sgc_colombia:2026-09-06-001",
            place: "59 km al SO de Los Santos, Santander",
            magnitude: 4.1,
            depthKm: 145.0,
            latitude: 6.78,
            longitude: -73.12,
            detectedAt: Date().addingTimeInterval(-7200),
            sourceId: "sgc_colombia",
            agency: "Servicio Geológico Colombiano (SGC)",
            isPreliminary: false,
            intensityMmi: 4,
            tsunamiWarning: false,
            magnitudeType: "Mw",
            reviewStatus: "manual",
            officialUrl: "https://www.sgc.gov.co"
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
            agency: "Servicio Geológico Colombiano (SGC)",
            isPreliminary: false,
            intensityMmi: 3,
            tsunamiWarning: false,
            magnitudeType: "Ml",
            reviewStatus: "manual"
        )
    ]
}

