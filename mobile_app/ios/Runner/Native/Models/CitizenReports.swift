import Foundation

/// Reporte ciudadano de sismo sentido (Did You Feel It / DYFI).
public struct FeltReportPayload: Codable {
    public let deviceId: String
    public let earthquakeEventId: String?
    public let officialEventId: String?
    public let observedAt: String
    public let latitude: Double
    public let longitude: Double
    public let countryCode: String
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

    enum CodingKeys: String, CodingKey {
        case deviceId = "device_id"
        case earthquakeEventId = "earthquake_event_id"
        case officialEventId = "official_event_id"
        case observedAt = "observed_at"
        case latitude
        case longitude
        case countryCode = "country_code"
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
    public let deviceId: String
    public let earthquakeEventId: String?
    public let officialEventId: String?
    public let observedAt: String
    public let latitude: Double
    public let longitude: Double
    public let countryCode: String
    public let severity: String
    public let hazards: [String]
    public let buildingType: String?
    public let peopleTrapped: Bool
    public let injuriesObserved: Bool
    public let emergencyServicesContacted: Bool
    public let safeToRemain: Bool?
    public let comment: String?

    enum CodingKeys: String, CodingKey {
        case deviceId = "device_id"
        case earthquakeEventId = "earthquake_event_id"
        case officialEventId = "official_event_id"
        case observedAt = "observed_at"
        case latitude
        case longitude
        case countryCode = "country_code"
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

/// Nivel de severidad de daños para el selector visual nativo.
public enum DamageSeverity: String, CaseIterable, Identifiable {
    case none = "none"
    case light = "light"
    case moderate = "moderate"
    case severe = "severe"
    case totalCollapse = "total_collapse"

    public var id: String { rawValue }

    public var title: String {
        switch self {
        case .none: return "Sin daños evidentes"
        case .light: return "Daños leves (grietas finas)"
        case .moderate: return "Daños moderados (fisuras, caída de mampostería)"
        case .severe: return "Daños graves (muros comprometidos)"
        case .totalCollapse: return "Colapso parcial o total"
        }
    }
}
