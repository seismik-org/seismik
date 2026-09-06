import SwiftUI

/// Cápsula flotante superior en Liquid Glass que aloja la identidad de Seismik y controles de red.
public struct FloatingHeaderView: View {
    @ObservedObject var state: SeismikState
    @Binding var showSettings: Bool

    @State private var rotationAngle: Double = 0

    public var body: some View {
        HStack(spacing: 12) {
            // Logotipo e Identidad
            HStack(spacing: 8) {
                Image(systemName: "waveform.path.ecg")
                    .font(.system(size: 17, weight: .bold))
                    .foregroundColor(SeismikColors.crimson)

                Text("SEISMIK")
                    .font(.system(size: 15, weight: .black, design: .rounded))
                    .tracking(2.2)
                    .foregroundColor(.primary)
            }

            Spacer()

            // Pastilla de Estado de Red
            HStack(spacing: 6) {
                Circle()
                    .fill(state.isOnline ? SeismikColors.emerald : SeismikColors.amber)
                    .frame(width: 8, height: 8)
                    .shadow(
                        color: (state.isOnline ? SeismikColors.emerald : SeismikColors.amber).opacity(0.8),
                        radius: 4
                    )

                Text(state.isOnline ? "En línea" : "Sin red")
                    .font(.system(size: 12, weight: .semibold, design: .rounded))
                    .foregroundColor(.secondary)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .background(.ultraThinMaterial, in: Capsule())

            // Botón de Recarga con Respuesta Háptica
            Button {
                HapticManager.light()
                withAnimation(.linear(duration: 0.8)) {
                    rotationAngle += 360
                }
                Task {
                    await state.refreshData()
                }
            } label: {
                Image(systemName: "arrow.clockwise")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(.primary)
                    .rotationEffect(.degrees(rotationAngle))
                    .frame(width: 32, height: 32)
                    .background(.ultraThinMaterial, in: Circle())
            }
            .buttonStyle(.plain)

            // Botón de Configuración
            Button {
                HapticManager.selection()
                showSettings = true
            } label: {
                Image(systemName: "gearshape")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(.primary)
                    .frame(width: 32, height: 32)
                    .background(.ultraThinMaterial, in: Circle())
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .liquidGlass(cornerRadius: 26)
        .padding(.horizontal, 16)
        .padding(.top, 4)
    }
}
