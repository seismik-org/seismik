import SwiftUI

/// Lista de sismos en la hoja nativa de iOS (alturas media y completa).
///
/// Antes era un panel propio que se arrastraba sobre el mapa con gestos y
/// alturas calculadas a mano. La hoja del sistema ya resuelve el arrastre, las
/// alturas, la accesibilidad y el cierre con un gesto que la gente conoce.
public struct SeismicSheetView: View {
    @ObservedObject var state: SeismikState
    @ObservedObject var locationManager: LocationManager

    // La hoja presenta sus propias hojas: desde la base no se puede presentar
    // otra mientras ésta sigue abierta.
    @State private var detailEvent: SeismicEvent?
    @State private var showFeltReport = false
    @State private var showDamageReport = false

    init(state: SeismikState, locationManager: LocationManager) {
        self.state = state
        self.locationManager = locationManager
    }

    public var body: some View {
        VStack(spacing: 0) {
            VStack(spacing: 0) {
                // Estado de sincronización / red exactamente como en Android
                HStack(spacing: 6) {
                    Circle()
                        .fill(state.isOnline ? SeismikColors.emerald : SeismikColors.amber)
                        .frame(width: 8, height: 8)
                    Text(state.isOnline ? "Sincronizado" : "Actualizando cuando vuelva la red")
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

                    Text("\(state.historyDays) días · M ≥ \(String(format: "%.1f", state.minMagnitude)) · Oficiales + preliminares")
                        .font(.system(size: 13, weight: .regular, design: .rounded))
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 18)
                .padding(.bottom, 12)

                // Barra de Acciones Rápidas Comunitarias
                HStack(spacing: 12) {
                    Button {
                        HapticManager.selection()
                        showFeltReport = true
                    } label: {
                        HStack(spacing: 6) {
                            Image(systemName: "hand.point.up.left.fill")
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
            .padding(.top, 22)

            Divider()

            // Reportes que esperan red y alertas recuperadas: la misma señal
            // que muestra la app de Android, para que nadie crea que un reporte
            // se perdió cuando en realidad está en cola.
            if state.pendingReportCount > 0 || state.syncMessage != nil {
                HStack(spacing: 10) {
                    Image(
                        systemName: state.pendingReportCount > 0
                            ? "arrow.up.circle"
                            : "checkmark.circle"
                    )
                    .foregroundColor(SeismikColors.systemBlue)
                    Text(state.syncMessage ?? pendingSummary)
                        .font(.system(size: 13))
                        .foregroundColor(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 0)
                    if state.pendingReportCount > 0 {
                        Button("Reintentar") {
                            Task { await state.flushPendingReports() }
                        }
                        .font(.system(size: 13, weight: .semibold))
                    }
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 10)
                Divider()
            }

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
                        systemImage: state.isOnline ? "waveform.path.ecg" : "wifi.slash",
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
                                detailEvent = event
                            }
                        }
                    }
                    .padding(.horizontal, 16)
                    .padding(.top, 12)
                    .padding(.bottom, 36)
                }
            }
        }
        .frame(maxHeight: .infinity, alignment: .top)
        .accessibilityElement(children: .contain)
        .sheet(item: $detailEvent) { event in
            EventDetailView(event: event)
        }
        .sheet(isPresented: $showFeltReport) {
            FeltReportView(preselectedEvent: state.events.first)
        }
        .sheet(isPresented: $showDamageReport) {
            DamageReportView(preselectedEvent: state.events.first)
        }
    }

    private var pendingSummary: String {
        state.pendingReportCount == 1
            ? "1 reporte espera conexión para enviarse."
            : "\(state.pendingReportCount) reportes esperan conexión para enviarse."
    }
}

/// Barra fija sobre las pestañas: resume el historial y abre la lista.
struct HistoryBarView: View {
    @ObservedObject var state: SeismikState
    let onOpen: () -> Void

    var body: some View {
        Button(action: onOpen) {
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 3) {
                    Text("Historial de sismos")
                        .font(.system(size: 16, weight: .bold, design: .rounded))
                        .foregroundColor(.primary)
                    Text(summary)
                        .font(.system(size: 13))
                        .foregroundColor(.secondary)
                        .lineLimit(1)
                }
                Spacer(minLength: 8)
                HStack(spacing: 5) {
                    Image(systemName: "list.bullet")
                    Text("Ver lista")
                }
                .font(.system(size: 14, weight: .semibold, design: .rounded))
                .foregroundColor(SeismikColors.systemBlue)
            }
            .padding(.horizontal, 16)
            .frame(maxWidth: .infinity, minHeight: 64)
            .liquidGlass(cornerRadius: 22)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityHint("Abre la lista de sismos")
    }

    private var summary: String {
        guard let latest = state.events.first else {
            return state.isRefreshing ? "Sincronizando red de sismos..." : "No hay sismos con estos filtros"
        }
        let magnitude = latest.magnitude.map { String(format: "M %.1f", $0) } ?? "Preliminar"
        return "\(magnitude) · \(latest.place ?? "Epicentro") · \(latest.relativeTimeFormatted)"
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
