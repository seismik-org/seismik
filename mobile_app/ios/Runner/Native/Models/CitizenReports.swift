import Foundation

/// Reporte ciudadano de sismo sentido (Did You Feel It / DYFI).
public struct FeltReportPayload: Codable {
    public let reportId: String
    public let deviceId: String
    public let type: String
    public let earthquakeEventId: String?
    public let officialEventId: String?
    public let observedAt: String
    public let latitude: Double
    public let longitude: Double
    public let locationPrecision: String
    public let countryCode: String
    public let consentVersion: String
    public let felt: Bool
    public let intensityMmi: Int?
    public let indoors: Bool?
    public let floor: Int?
    public let wokeUp: Bool?
    public let difficultyStanding: Bool?
    public let objectsMoved: Bool?
    public let objectsFell: Bool?
    public let visibleDamage: Bool?
    public let comment: String?

    public init(
        reportId: String = UUID().uuidString,
        deviceId: String,
        earthquakeEventId: String?,
        officialEventId: String?,
        observedAt: String = ISO8601DateFormatter().string(from: Date()),
        latitude: Double,
        longitude: Double,
        locationPrecision: String = "precise",
        countryCode: String,
        consentVersion: String = "2026-08",
        felt: Bool,
        intensityMmi: Int?,
        indoors: Bool?,
        floor: Int?,
        wokeUp: Bool?,
        difficultyStanding: Bool?,
        objectsMoved: Bool? = nil,
        objectsFell: Bool? = nil,
        visibleDamage: Bool? = nil,
        comment: String? = nil
    ) {
        self.reportId = reportId
        self.deviceId = deviceId
        self.type = "seismik_felt_report"
        self.earthquakeEventId = earthquakeEventId
        self.officialEventId = officialEventId
        self.observedAt = observedAt
        self.latitude = latitude
        self.longitude = longitude
        self.locationPrecision = locationPrecision
        self.countryCode = countryCode
        self.consentVersion = consentVersion
        self.felt = felt
        self.intensityMmi = felt ? intensityMmi : nil
        self.indoors = indoors
        self.floor = floor
        self.wokeUp = wokeUp
        self.difficultyStanding = difficultyStanding
        self.objectsMoved = objectsMoved
        self.objectsFell = objectsFell
        self.visibleDamage = visibleDamage
        self.comment = comment
    }

    enum CodingKeys: String, CodingKey {
        case reportId = "report_id"
        case deviceId = "device_id"
        case type
        case earthquakeEventId = "earthquake_event_id"
        case officialEventId = "official_event_id"
        case observedAt = "observed_at"
        case latitude
        case longitude
        case locationPrecision = "location_precision"
        case countryCode = "country_code"
        case consentVersion = "consent_version"
        case felt
        case intensityMmi = "intensity_mmi"
        case indoors
        case floor
        case wokeUp = "woke_up"
        case difficultyStanding = "difficulty_standing"
        case objectsMoved = "objects_moved"
        case objectsFell = "objects_fell"
        case visibleDamage = "visible_damage"
        case comment
    }
}

/// Reporte ciudadano de daños estructurales y emergencias.
public struct DamageReportPayload: Codable {
    public let reportId: String
    public let deviceId: String
    public let type: String
    public let earthquakeEventId: String?
    public let officialEventId: String?
    public let observedAt: String
    public let latitude: Double
    public let longitude: Double
    public let locationPrecision: String
    public let countryCode: String
    public let consentVersion: String
    public let severity: String
    public let hazards: [String]
    public let buildingType: String?
    public let peopleTrapped: Bool
    public let injuriesObserved: Bool
    public let emergencyServicesContacted: Bool
    public let safeToRemain: Bool?
    public let comment: String?

    public init(
        reportId: String = UUID().uuidString,
        deviceId: String,
        earthquakeEventId: String?,
        officialEventId: String?,
        observedAt: String = ISO8601DateFormatter().string(from: Date()),
        latitude: Double,
        longitude: Double,
        locationPrecision: String = "precise",
        countryCode: String,
        consentVersion: String = "2026-08",
        severity: String,
        hazards: [String] = [],
        buildingType: String? = nil,
        peopleTrapped: Bool = false,
        injuriesObserved: Bool = false,
        emergencyServicesContacted: Bool = false,
        safeToRemain: Bool? = nil,
        comment: String? = nil
    ) {
        self.reportId = reportId
        self.deviceId = deviceId
        self.type = "seismik_damage_report"
        self.earthquakeEventId = earthquakeEventId
        self.officialEventId = officialEventId
        self.observedAt = observedAt
        self.latitude = latitude
        self.longitude = longitude
        self.locationPrecision = locationPrecision
        self.countryCode = countryCode
        self.consentVersion = consentVersion
        self.severity = severity
        self.hazards = hazards
        self.buildingType = buildingType
        self.peopleTrapped = peopleTrapped
        self.injuriesObserved = injuriesObserved
        self.emergencyServicesContacted = emergencyServicesContacted
        self.safeToRemain = safeToRemain
        self.comment = comment
    }

    enum CodingKeys: String, CodingKey {
        case reportId = "report_id"
        case deviceId = "device_id"
        case type
        case earthquakeEventId = "earthquake_event_id"
        case officialEventId = "official_event_id"
        case observedAt = "observed_at"
        case latitude
        case longitude
        case locationPrecision = "location_precision"
        case countryCode = "country_code"
        case consentVersion = "consent_version"
        case severity
        case hazards
        case buildingType = "building_type"
        case peopleTrapped = "people_trapped"
        case injuriesObserved = "injuries_observed"
        case emergencyServicesContacted = "emergency_services_contacted"
        case safeToRemain = "safe_to_remain"
        case comment
    }
}

/// Nivel de severidad de daños para el selector visual nativo (compatible con backend).
public enum DamageSeverity: String, CaseIterable, Identifiable {
    case none = "none"
    case minor = "minor"
    case moderate = "moderate"
    case severe = "severe"
    case collapse = "collapse"

    public var id: String { rawValue }

    public var title: String {
        switch self {
        case .none: return "Sin daños evidentes"
        case .minor: return "Daños leves (grietas finas)"
        case .moderate: return "Daños moderados (fisuras, caída de mampostería)"
        case .severe: return "Daños graves (muros comprometidos)"
        case .collapse: return "Colapso parcial o total"
        }
    }
}

/// Peligros observables en un reporte de daños.
///
/// Los `rawValue` son los identificadores que acepta `ObservedHazard` en el
/// backend y los mismos que ofrece la app de Android. Un valor inventado aquí
/// se traduce en un 422 que sólo aparece con el reporte ya escrito.
public enum ObservedHazard: String, CaseIterable, Identifiable {
    case fire
    case gasLeak = "gas_leak"
    case electrical
    case waterLeak = "water_leak"
    case landslide
    case roadBlocked = "road_blocked"
    case structuralInstability = "structural_instability"

    public var id: String { rawValue }

    public var title: String {
        switch self {
        case .fire: return "Incendio"
        case .gasLeak: return "Fuga de gas u olor persistente"
        case .electrical: return "Cables caídos o riesgo eléctrico"
        case .waterLeak: return "Fuga de agua"
        case .landslide: return "Deslizamiento"
        case .roadBlocked: return "Vía bloqueada"
        case .structuralInstability: return "Estructura inestable"
        }
    }
}
