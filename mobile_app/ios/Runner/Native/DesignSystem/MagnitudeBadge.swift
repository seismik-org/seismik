import SwiftUI

/// Insignia flotante para representar la magnitud de un sismo con colores joya.
public struct MagnitudeBadge: View {
    public let magnitude: Double?
    public let isPreliminary: Bool
    public let customText: String?
    public let fontSize: CGFloat

    public init(
        magnitude: Double?,
        isPreliminary: Bool = false,
        customText: String? = nil,
        fontSize: CGFloat = 15
    ) {
        self.magnitude = magnitude
        self.isPreliminary = isPreliminary
        self.customText = customText
        self.fontSize = fontSize
    }

    private var displayText: String {
        if let custom = customText { return custom }
        if isPreliminary { return "P" }
        guard let mag = magnitude else { return "—" }
        return String(format: "%.1f", mag)
    }

    public var body: some View {
        Text(displayText)
            .font(.system(size: fontSize, weight: .bold, design: .rounded))
            .foregroundColor(.white)
            .padding(.horizontal, isPreliminary ? 9 : 11)
            .padding(.vertical, 6)
            .background {
                ZStack {
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .fill(SeismikColors.severityGradient(for: magnitude, isPreliminary: isPreliminary))

                    // Bisel superior iluminado
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .strokeBorder(
                            LinearGradient(
                                colors: [
                                    Color.white.opacity(0.80),
                                    Color.white.opacity(0.20)
                                ],
                                startPoint: .top,
                                endPoint: .bottom
                            ),
                            lineWidth: 0.75
                        )
                }
            }
            .shadow(
                color: SeismikColors.severityColor(for: magnitude, isPreliminary: isPreliminary).opacity(0.35),
                radius: 6,
                x: 0,
                y: 3
            )
    }
}
