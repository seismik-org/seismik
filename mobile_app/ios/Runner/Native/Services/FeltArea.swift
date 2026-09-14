import Foundation
import MapKit

/// Numerical parity with src/api/felt_area.py. Distances are kilometres.
enum FeltArea {
    static let felt = 3.0
    static let strong = 6.0
    static let maximumRadiusKm = 2_000.0

    struct Ring: Equatable, Identifiable {
        let intensity: Double
        let radiusKm: Double
        let label: String
        var id: Double { intensity }
    }

    static func distanceKm(from a: CLLocationCoordinate2D, to b: CLLocationCoordinate2D) -> Double {
        let radians = Double.pi / 180
        let inner = pow(sin((b.latitude - a.latitude) * radians / 2), 2)
            + cos(a.latitude * radians) * cos(b.latitude * radians)
            * pow(sin((b.longitude - a.longitude) * radians / 2), 2)
        return 2 * 6371.0088 * asin(min(1, sqrt(max(0, inner))))
    }

    static func intensity(magnitude m: Double, depthKm: Double?, distanceKm: Double) -> Double {
        let depth = depthKm.flatMap { $0 >= 0 ? $0 : nil } ?? 10
        let d = max(1, hypot(distanceKm, depth))
        let weight = min(1, max(0, (depth - 40) / 30))
        var result = 0.0
        if weight < 1 {
            let near = -0.209 + 2.042 * exp(m - 5)
            var crustal = 2.085 + 1.428 * m - 1.402 * log(sqrt(d * d + near * near))
            if d > 50 { crustal += 0.078 * log(d / 50) }
            result += (1 - weight) * crustal
        }
        if weight > 0 {
            let h = min(depth, 125)
            var lnPGA = 1.101 * m - 0.00564 * d - log(d + 0.0055 * exp(1.080 * m))
            lnPGA += h >= 15 ? 0.01412 * (h - 15) : 0
            lnPGA += 1.344 + 0.1392 * (m - 6.5) + 0.1584 * pow(m - 6.5, 2)
            lnPGA += -0.0529 + 2.607 - 0.528 * log(d)
            let logPGA = lnPGA / log(10)
            result += weight * (logPGA <= 1.57 ? 1.78 + 1.55 * logPGA : -1.60 + 3.70 * logPGA)
        }
        return min(12, max(1, result))
    }

    static func radiusKm(magnitude: Double, depthKm: Double?, threshold: Double = felt) -> Double? {
        func at(_ distance: Double) -> Double {
            intensity(magnitude: magnitude, depthKm: depthKm, distanceKm: distance)
        }
        guard at(0) >= threshold else { return nil }
        if at(maximumRadiusKm) >= threshold { return maximumRadiusKm }
        var low = 0.0
        var high = maximumRadiusKm
        for _ in 0..<40 {
            let middle = (low + high) / 2
            if at(middle) >= threshold { low = middle } else { high = middle }
        }
        return low
    }

    static func roman(_ intensity: Double) -> String {
        let level = min(12, max(1, Int(floor(intensity + 0.5))))
        return ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"][level - 1]
    }

    static func name(_ intensity: Double) -> String {
        switch min(12, max(1, Int(floor(intensity + 0.5)))) {
        case 1: return "no sentido"
        case 2, 3: return "débil"
        case 4: return "ligero"
        case 5: return "moderado"
        case 6: return "fuerte"
        case 7: return "muy fuerte"
        case 8: return "severo"
        case 9: return "violento"
        default: return "extremo"
        }
    }

    static func perimeter(for event: SeismicEvent) -> [Ring] {
        guard let magnitude = event.magnitude, magnitude.isFinite,
              let coordinate = event.coordinate, CLLocationCoordinate2DIsValid(coordinate) else { return [] }
        let levels: [(Double, String)] = [(3, "Se sintió"), (4, "Sacudida ligera"),
                                         (6, "Sacudida fuerte"), (8, "Sacudida severa")]
        return levels.compactMap { level, label in
            radiusKm(magnitude: magnitude, depthKm: event.depthKm, threshold: level)
                .map { Ring(intensity: level, radiusKm: $0, label: label) }
        }
    }

    static func localIntensity(for event: SeismicEvent, at location: CLLocationCoordinate2D?) -> Double? {
        guard let magnitude = event.magnitude, let epicenter = event.coordinate,
              let location else { return nil }
        return intensity(magnitude: magnitude, depthKm: event.depthKm,
                         distanceKm: distanceKm(from: epicenter, to: location))
    }

    static func recentEvents(_ events: [SeismicEvent], now: Date = Date()) -> [SeismicEvent] {
        Array(events.filter {
            guard let date = $0.detectedAt else { return false }
            return date >= now.addingTimeInterval(-72 * 3600) && !perimeter(for: $0).isEmpty
        }.prefix(30))
    }

    static func color(_ intensity: Double) -> UIColor {
        let hex: Int
        switch intensity {
        case 8...: hex = 0x8E0012
        case 6...: hex = 0xE53935
        case 4...: hex = 0xFB8C00
        default: hex = 0xFFB300
        }
        return UIColor(red: CGFloat((hex >> 16) & 255) / 255,
                       green: CGFloat((hex >> 8) & 255) / 255,
                       blue: CGFloat(hex & 255) / 255, alpha: 1)
    }

    static func circle(_ ring: Ring, center: CLLocationCoordinate2D) -> MKCircle {
        let circle = MKCircle(center: center, radius: ring.radiusKm * 1_000)
        circle.title = String(ring.intensity)
        return circle
    }

    static func renderer(for circle: MKCircle) -> MKCircleRenderer {
        let level = Double(circle.title ?? "3") ?? 3
        let renderer = MKCircleRenderer(circle: circle)
        renderer.strokeColor = color(level).withAlphaComponent(0.85)
        renderer.fillColor = color(level).withAlphaComponent(level == 3 ? 0.08 : 0.14)
        renderer.lineWidth = level == 3 ? 2 : 1
        return renderer
    }

    static let sourceNote = "Estimación con modelos de atenuación publicados (Allen 2012; Zhao 2006 y Worden 2012). La sacudida real cambia con el suelo y la construcción: si lo sentiste, repórtalo."
}
