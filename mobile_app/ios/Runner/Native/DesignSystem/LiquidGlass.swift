import SwiftUI

/// Usa Liquid Glass real en iOS 26 y un material sobrio en versiones anteriores.
/// No dibuja gradientes ni biseles que compitan con la apariencia del sistema.
public struct LiquidGlassModifier: ViewModifier {
    public let cornerRadius: CGFloat
    public let tint: Color?
    public let showShadow: Bool

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
        let shape = RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
        if #available(iOS 26.0, *) {
            if let tint {
                content
                    .glassEffect(.regular.tint(tint).interactive(), in: shape)
                    .shadow(color: showShadow ? .black.opacity(0.10) : .clear, radius: 10, y: 4)
            } else {
                content
                    .glassEffect(.regular.interactive(), in: shape)
                    .shadow(color: showShadow ? .black.opacity(0.10) : .clear, radius: 10, y: 4)
            }
        } else {
            content
                .background(.ultraThinMaterial, in: shape)
                .overlay {
                    if let tint {
                        shape.fill(tint.opacity(0.10))
                    }
                }
                .clipShape(shape)
                .shadow(color: showShadow ? .black.opacity(0.10) : .clear, radius: 10, y: 4)
        }
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

    /// Presentación de hoja sísmica con detents elásticos en iOS 16+ y soporte transparente en iOS 15+.
    @ViewBuilder
    public func seismicSheetPresentation() -> some View {
        if #available(iOS 16.4, *) {
            self
                .presentationDetents([.fraction(0.18), .medium, .large])
                .presentationDragIndicator(.visible)
                .presentationBackgroundInteraction(.enabled(upThrough: .medium))
        } else if #available(iOS 16.0, *) {
            self
                .presentationDetents([.fraction(0.18), .medium, .large])
                .presentationDragIndicator(.visible)
        } else {
            self
        }
    }

    /// Presentación de hoja modal estándar con detents en iOS 16+ y soporte transparente en iOS 15+.
    @ViewBuilder
    public func modalSheetPresentation() -> some View {
        if #available(iOS 16.0, *) {
            self
                .presentationDetents([.medium, .large])
                .presentationDragIndicator(.visible)
        } else {
            self
        }
    }
}

// MARK: - Contenedor de Navegación Compatible (iOS 15 - iOS 18+)
public struct CompatibleNavigationStack<Content: View>: View {
    @ViewBuilder private let content: () -> Content

    public init(@ViewBuilder content: @escaping () -> Content) {
        self.content = content
    }

    public var body: some View {
        if #available(iOS 16.0, *) {
            NavigationStack {
                content()
            }
        } else {
            NavigationView {
                content()
            }
            .navigationViewStyle(.stack)
        }
    }
}
