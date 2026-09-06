import SwiftUI

/// Vista de contenido para la hoja inferior interactiva de sismos.
public struct SeismicSheetView: View {
    @ObservedObject var state: SeismikState
    @ObservedObject var locationManager: LocationManager

    @Binding var showFeltReport: Bool
    @Binding var showDamageReport: Bool
    let onDrawerDragChanged: (CGFloat) -> Void
    let onDrawerDragEnded: (CGFloat) -> Void
    let onDrawerHandleTapped: () -> Void

    public var body: some View {
            VStack(spacing: 0) {
                // Manija táctil de arrastre
                Capsule()
                    .fill(Color.secondary.opacity(0.38))
                    .frame(width: 38, height: 5)
                    .frame(maxWidth: .infinity, minHeight: 24)
                    .contentShape(Rectangle())

                // Estado de sincronización / red exactamente como en Android
                HStack(spacing: 6) {
                    Circle()
                        .fill(state.isOnline ? SeismikColors.emerald : SeismikColors.amber)
                        .frame(width: 8, height: 8)
                    Text(state.isOnline ? "En línea" : "Reconectando con Seismik")
                        .font(.system(size: 12.5, weight: .medium, design: .rounded))
                        .foregroundColor(state.isOnline ? .secondary : SeismikColors.amber)
                    Spacer()
                    Text("\(state.events.count) eventos")
                        .font(.system(size: 12, weight: .medium, design: .rounded))
                        .foregroundColor(.secondary)
                }
                .padding(.horizontal, 18)
                .padding(.bottom, 2)

                // Título y subtítulo con paridad total con Android
                VStack(alignment: .leading, spacing: 2) {
                    Text("Historial de sismos")
                        .font(.system(size: 22, weight: .bold, design: .rounded))
                        .foregroundColor(.primary)

                    Text("\(state.historyDays) días · M ≥ \(String(format: "%.1f", state.minMagnitude)) · SGC + USGS")
                        .font(.system(size: 13, weight: .regular, design: .rounded))
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 18)
                .padding(.bottom, 10)

                // Barra de Acciones Rápidas Comunitarias
                HStack(spacing: 12) {
                    Button {
                        HapticManager.selection()
                        showFeltReport = true
                    } label: {
                        HStack(spacing: 6) {
                            Image(systemName: "hand.tap.fill")
                                .font(.system(size: 13, weight: .semibold))
                            Text("¿Lo sentiste?")
                                .font(.system(size: 13, weight: .semibold, design: .rounded))
                        }
                        .foregroundColor(.primary)
                        .frame(maxWidth: .infinity, minHeight: 44)
                        .liquidGlass(cornerRadius: 14, showShadow: false)
                    }
                    .buttonStyle(.plain)

                    Button {
                        HapticManager.selection()
                        showDamageReport = true
                    } label: {
                        HStack(spacing: 6) {
                            Image(systemName: "house.fill")
                                .font(.system(size: 13, weight: .semibold))
                            Text("Reportar daños")
                                .font(.system(size: 13, weight: .semibold, design: .rounded))
                        }
                        .foregroundColor(.primary)
                        .frame(maxWidth: .infinity, minHeight: 44)
                        .liquidGlass(cornerRadius: 14, showShadow: false)
                    }
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, 16)
                .padding(.bottom, 12)
            }
            .contentShape(Rectangle())
            .simultaneousGesture(
                DragGesture(minimumDistance: 4)
                    .onChanged { value in
                        onDrawerDragChanged(value.translation.height)
                    }
                    .onEnded { value in
                        onDrawerDragEnded(value.predictedEndTranslation.height)
                    }
            )
            .onTapGesture {
                onDrawerHandleTapped()
            }

            Divider()

            // Listado equivalente a los puntos del mapa, útil también con VoiceOver.
            if state.events.isEmpty {
                if state.isRefreshing {
                    VStack(spacing: 12) {
                        Spacer()
                        ProgressView()
                        Text("Sincronizando red de sismos...")
                            .font(.system(size: 14, weight: .medium))
                            .foregroundColor(.secondary)
                        Spacer()
                    }
                } else {
                    ContentUnavailableViewCompat(
                        title: state.isOnline ? "No hay sismos con estos filtros" : "No se pudo conectar",
                        systemImage: state.isOnline ? "waveform.path.ecg" : "wifi.exclamationmark",
                        description: state.isOnline
                            ? "Prueba un periodo mayor o una magnitud menor."
                            : "Comprueba tu conexión y vuelve a intentarlo."
                    )
                }
            } else {
                ScrollView {
                    LazyVStack(spacing: 10) {
                        ForEach(state.events) { event in
                            let distance = event.coordinate.flatMap { locationManager.distance(to: $0) }
                            EventRowView(
                                event: event,
                                userDistanceKm: distance
                            ) {
                                state.selectEvent(event)
                            }
                        }
                    }
                    .padding(.horizontal, 16)
                    .padding(.bottom, 36)
                }
            }
        }
        .background(
            RoundedRectangle(cornerRadius: 28, style: .continuous)
                .fill(.ultraThinMaterial)
                .ignoresSafeArea(edges: .bottom)
        )
        .clipShape(RoundedRectangle(cornerRadius: 28, style: .continuous))
        .shadow(color: Color.black.opacity(0.16), radius: 18, x: 0, y: -4)
        .accessibilityElement(children: .contain)
    }
}

private struct ContentUnavailableViewCompat: View {
    let title: String
    let systemImage: String
    let description: String

    var body: some View {
        VStack(spacing: 10) {
            Spacer(minLength: 16)
            Image(systemName: systemImage)
                .font(.system(size: 28, weight: .medium))
                .foregroundColor(.secondary)
                .accessibilityHidden(true)
            Text(title)
                .font(.headline)
                .multilineTextAlignment(.center)
            Text(description)
                .font(.subheadline)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
            Spacer(minLength: 16)
        }
        .padding(.horizontal, 28)
    }
}
