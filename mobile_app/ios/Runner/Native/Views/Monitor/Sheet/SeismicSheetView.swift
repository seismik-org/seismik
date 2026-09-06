import SwiftUI

/// Vista de contenido para la hoja inferior interactiva de sismos.
public struct SeismicSheetView: View {
    @ObservedObject var state: SeismikState
    @ObservedObject var locationManager: LocationManager

    @Binding var showFeltReport: Bool
    @Binding var showDamageReport: Bool

    public var body: some View {
        CompatibleNavigationStack {
            VStack(spacing: 0) {
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
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 10)
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
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 10)
                        .liquidGlass(cornerRadius: 14, showShadow: false)
                    }
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, 16)
                .padding(.top, 12)
                .padding(.bottom, 10)

                // Listado de Sismos
                if state.events.isEmpty {
                    VStack(spacing: 12) {
                        Spacer()
                        ProgressView()
                            .scaleEffect(1.2)
                        Text("Sincronizando red de sismos...")
                            .font(.system(size: 14, weight: .medium))
                            .foregroundColor(.secondary)
                        Spacer()
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
            .navigationTitle("Sismos Recientes")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Text("\(state.events.count) eventos")
                        .font(.system(size: 13, weight: .medium, design: .rounded))
                        .foregroundColor(.secondary)
                }
            }
        }
        .background(.ultraThinMaterial)
    }
}
