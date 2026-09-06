import SwiftUI

/// Modificador de vista que otorga la apariencia auténtica de Liquid Glass nativo en iOS.
///
/// Combina el material físico del sistema (`.ultraThinMaterial`), la curvatura
/// continua de Apple (`.continuous` squircle), un bisel especular de luz superior
/// y sombras ambientales de baja dispersión.
public struct LiquidGlassModifier: ViewModifier {
    public let cornerRadius: CGFloat
    public let tint: Color?
    public let showShadow: Bool

    @Environment(\.colorScheme) private var colorScheme

    public init(
        cornerRadius: CGFloat = 20,
        tint: Color? = nil,
        showShadow: Bool = true
    ) {
        self.cornerRadius = cornerRadius
        self.tint = tint
        self.showShadow = showShadow
    }

    public func body(content: Content) -> some View {
        let isDark = colorScheme == .dark
        let shape = RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)

        content
            .background {
                ZStack {
                    // Material físico del sistema con desenfoque de GPU
                    shape
                        .fill(.ultraThinMaterial)

                    // Tinte sutil opcional (para severidad, alertas o modo noche)
                    if let tint = tint {
                        shape
                            .fill(tint.opacity(isDark ? 0.22 : 0.14))
                    }

                    // Tinte direccional de iluminación ambiental
                    shape
                        .fill(
                            LinearGradient(
                                colors: [
                                    Color.white.opacity(isDark ? 0.08 : 0.40),
                                    Color.white.opacity(isDark ? 0.01 : 0.08)
                                ],
                                startPoint: .top,
                                endPoint: .bottom
                            )
                        )
                }
            }
            .clipShape(shape)
            .overlay {
                // Bisel especular de luz: simula la refracción en el borde del cristal
                shape
                    .strokeBorder(
                        LinearGradient(
                            colors: [
                                Color.white.opacity(isDark ? 0.45 : 0.85),
                                Color.white.opacity(isDark ? 0.08 : 0.20)
                            ],
                            startPoint: .top,
                            endPoint: .bottom
                        ),
                        lineWidth: 0.65
                    )
            }
            .shadow(
                color: showShadow
                    ? Color.black.opacity(isDark ? 0.35 : 0.09)
                    : Color.clear,
                radius: isDark ? 16 : 12,
                x: 0,
                y: isDark ? 6 : 4
            )
    }
}

// MARK: - View Extension
extension View {
    /// Aplica el acabado Liquid Glass estilo Apple HIG.
    public func liquidGlass(
        cornerRadius: CGFloat = 20,
        tint: Color? = nil,
        showShadow: Bool = true
    ) -> some View {
        modifier(
            LiquidGlassModifier(
                cornerRadius: cornerRadius,
                tint: tint,
                showShadow: showShadow
            )
        )
    }

    /// Aplica el acabado Liquid Glass en formato de cápsula.
    public func glassCapsule(
        tint: Color? = nil,
        showShadow: Bool = true
    ) -> some View {
        self
            .padding(.horizontal, 14)
            .padding(.vertical, 8)
            .liquidGlass(cornerRadius: 30, tint: tint, showShadow: showShadow)
    }
}
