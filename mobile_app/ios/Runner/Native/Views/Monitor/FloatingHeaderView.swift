import SwiftUI

/// Controles discretos del mapa. El estado de red vive en la hoja de historial.
public struct FloatingHeaderView: View {
    @ObservedObject var state: SeismikState
    @Binding var showSettings: Bool

    @State private var rotationAngle: Double = 0

    public var body: some View {
        HStack(spacing: 10) {
            Spacer()
            Button {
                HapticManager.light()
                withAnimation(.linear(duration: 0.55)) { rotationAngle += 360 }
                Task { await state.refreshData() }
            } label: {
                Image(systemName: "arrow.clockwise")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundStyle(.primary)
                    .rotationEffect(.degrees(rotationAngle))
                    .frame(width: 44, height: 44)
                    .background(.ultraThinMaterial, in: Circle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Actualizar sismos")

            Button {
                HapticManager.selection()
                showSettings = true
            } label: {
                Image(systemName: "gearshape")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundStyle(.primary)
                    .frame(width: 44, height: 44)
                    .background(.ultraThinMaterial, in: Circle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Abrir configuración")
        }
        .padding(.trailing, 18)
        .padding(.top, 4)
    }
}
