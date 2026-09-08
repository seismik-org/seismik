import SwiftUI
import UIKit

/// Paleta de color semántica alineada con Apple Human Interface Guidelines (HIG).
public enum SeismikColors {
    // Tonos principales de sistema
    public static let obsidian = Color(hex: "0B0E14")
    public static let systemBlue = Color(red: 0.0, green: 0.478, blue: 1.0)
    public static let emerald = Color(red: 0.188, green: 0.820, blue: 0.345)
    public static let amber = Color(red: 1.0, green: 0.624, blue: 0.039)
    public static let crimson = Color(red: 1.0, green: 0.271, blue: 0.227)
    public static let glacier = Color(red: 0.196, green: 0.678, blue: 0.902)
    public static let lavender = Color(red: 0.749, green: 0.353, blue: 0.949)

    // Superficies de cristal
    public static let glassHighlight = Color.white.opacity(0.65)
    public static let glassShadow = Color.black.opacity(0.18)

    /// Color representativo de acuerdo con la magnitud del sismo.
    public static func severityColor(for magnitude: Double?, isPreliminary: Bool = false) -> Color {
        if isPreliminary { return lavender }
        guard let mag = magnitude else { return Color.secondary }
        switch mag {
        case ..<3.5:
            return emerald
        case 3.5..<4.8:
            return glacier
        case 4.8..<6.0:
            return amber
        default:
            return crimson
        }
    }

    /// Color representativo para UIKit de acuerdo con la magnitud del sismo.
    public static func severityUIColor(for magnitude: Double?, isPreliminary: Bool = false) -> UIColor {
        if isPreliminary {
            return UIColor(red: 0.749, green: 0.353, blue: 0.949, alpha: 1.0)
        }
        guard let mag = magnitude else { return UIColor.secondaryLabel }
        switch mag {
        case ..<3.5:
            return UIColor(red: 0.188, green: 0.820, blue: 0.345, alpha: 1.0)
        case 3.5..<4.8:
            return UIColor(red: 0.196, green: 0.678, blue: 0.902, alpha: 1.0)
        case 4.8..<6.0:
            return UIColor(red: 1.0, green: 0.624, blue: 0.039, alpha: 1.0)
        default:
            return UIColor(red: 1.0, green: 0.271, blue: 0.227, alpha: 1.0)
        }
    }

    /// Gradiente joya (jewel-tone) para el fondo de la pastilla de magnitud.
    public static func severityGradient(for magnitude: Double?, isPreliminary: Bool = false) -> LinearGradient {
        let base = severityColor(for: magnitude, isPreliminary: isPreliminary)
        return LinearGradient(
            gradient: Gradient(colors: [
                base.opacity(0.95),
                base.opacity(0.72)
            ]),
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    }
}

// MARK: - Color Hex Extension
extension Color {
    public init(hex: String) {
        let hex = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        var int: UInt64 = 0
        Scanner(string: hex).scanHexInt64(&int)
        let a, r, g, b: UInt64
        switch hex.count {
        case 3: // RGB (12-bit)
            (a, r, g, b) = (255, (int >> 8) * 17, (int >> 4 & 0xF) * 17, (int & 0xF) * 17)
        case 6: // RGB (24-bit)
            (a, r, g, b) = (255, int >> 16, int >> 8 & 0xFF, int & 0xFF)
        case 8: // ARGB (32-bit)
            (a, r, g, b) = (int >> 24, int >> 16 & 0xFF, int >> 8 & 0xFF, int & 0xFF)
        default:
            (a, r, g, b) = (255, 0, 0, 0)
        }
        self.init(
            .sRGB,
            red: Double(r) / 255,
            green: Double(g) / 255,
            blue: Double(b) / 255,
            opacity: Double(a) / 255
        )
    }
}
