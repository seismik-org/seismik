import SwiftUI

/// Pantalla de alerta sísmica crítica inmersiva con material carmesí profundo y respiración lumínica.
public struct EmergencyAlertView: View {
    public let event: SeismicEvent
    public let onDismiss: () -> Void
    /// Cierra la alerta y lleva a avisar a la familia.
    public var onReportSafe: (() -> Void)? = nil

    @State private var isPulsing: Bool = false

    public var body: some View {
        ZStack {
            // Fondo oscuro con tinte carmesí profundo y material de vidrio
            Color.black.opacity(0.85).ignoresSafeArea()

            RadialGradient(
                colors: [
                    SeismikColors.crimson.opacity(isPulsing ? 0.75 : 0.40),
                    Color.black.opacity(0.92)
                ],
                center: .center,
                startRadius: 40,
                endRadius: 360
            )
            .ignoresSafeArea()
            .animation(.easeInOut(duration: 1.4).repeatForever(autoreverses: true), value: isPulsing)

            VStack(spacing: 24) {
                Spacer()

                // Encabezado de Alarma
                VStack(spacing: 8) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .font(.system(size: 48))
                        .foregroundColor(SeismikColors.crimson)
                        .shadow(color: SeismikColors.crimson.opacity(0.9), radius: 18)

                    Text("ALERTA SÍSMICA")
                        .font(.system(size: 28, weight: .black, design: .rounded))
                        .tracking(3.0)
                        .foregroundColor(.white)

                    Text(event.place ?? "Sismo detectado en tu región")
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundColor(.white.opacity(0.9))
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 24)
                }

                // Se evita una cuenta regresiva inventada: solo se muestra tiempo si el
                // backend llega a calcularlo con coordenadas y velocidades verificadas.
                VStack(spacing: 6) {
                    Text("PROTÉGETE AHORA")
                        .font(.system(size: 28, weight: .black, design: .rounded))
                        .foregroundColor(.white)

                    if let magnitude = event.magnitude {
                        Text("Magnitud estimada \(String(format: "%.1f", magnitude))")
                            .font(.system(size: 15, weight: .semibold, design: .rounded))
                            .foregroundColor(.white.opacity(0.9))
                    } else {
                        Text("Movimiento sísmico detectado")
                            .font(.system(size: 15, weight: .semibold, design: .rounded))
                            .foregroundColor(.white.opacity(0.9))
                    }
                }
                .padding(.horizontal, 28)
                .padding(.vertical, 16)
                .liquidGlass(cornerRadius: 26, tint: SeismikColors.crimson)

                // Pasos de Seguridad Inmediatos
                VStack(spacing: 12) {
                    AlertStepRow(number: "1", title: "AGÁCHATE", desc: "Reduce tu centro de gravedad.")
                    AlertStepRow(number: "2", title: "CÚBRETE", desc: "Protege cabeza y cuello bajo un mueble firme.")
                    AlertStepRow(number: "3", title: "SUJÉTATE", desc: "Permanece cubierto hasta que cese el movimiento.")
                }
                .padding(.horizontal, 24)

                Spacer()

                if let onReportSafe {
                    Button {
                        HapticManager.heavy()
                        AlertSoundPlayer.shared.stop()
                        onReportSafe()
                    } label: {
                        Label("Avisar a mi familia", systemImage: "person.2.fill")
                            .font(.system(size: 16, weight: .bold))
                            .foregroundColor(SeismikColors.crimson)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 16)
                            .background(Color.white, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
                    }
                    .buttonStyle(.plain)
                    .padding(.horizontal, 24)
                }

                // Botón de Cierre Seguro
                Button {
                    HapticManager.heavy()
                    AlertSoundPlayer.shared.stop()
                    onDismiss()
                } label: {
                    Text("Estoy a salvo / Descartar")
                        .font(.system(size: 16, weight: .bold))
                        .foregroundColor(.white)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 16)
                        .liquidGlass(cornerRadius: 20, tint: Color.white.opacity(0.2))
                }
                .buttonStyle(.plain)
                .padding(.horizontal, 24)
                .padding(.bottom, 20)
            }
        }
        .onAppear {
            isPulsing = true
            HapticManager.heavy()
            AlertSoundPlayer.shared.playSiren()
        }
        .onDisappear {
            AlertSoundPlayer.shared.stop()
        }
    }
}

// MARK: - Fila de Paso de Seguridad en Alerta
private struct AlertStepRow: View {
    let number: String
    let title: String
    let desc: String

    var body: some View {
        HStack(spacing: 14) {
            Text(number)
                .font(.system(size: 20, weight: .black, design: .rounded))
                .foregroundColor(.white)
                .frame(width: 36, height: 36)
                .background(SeismikColors.crimson, in: Circle())

            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.system(size: 14, weight: .bold))
                    .foregroundColor(.white)
                Text(desc)
                    .font(.system(size: 12))
                    .foregroundColor(.white.opacity(0.85))
            }
            Spacer()
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .liquidGlass(cornerRadius: 16, tint: Color.white.opacity(0.15), showShadow: false)
    }
}
