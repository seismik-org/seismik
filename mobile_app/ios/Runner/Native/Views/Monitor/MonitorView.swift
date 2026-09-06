import SwiftUI
import MapKit

/// Vista principal de monitoreo con Apple MapKit interactivo a pantalla completa y hoja de sismos nativa.
public struct MonitorView: View {
    @StateObject private var state = SeismikState.shared
    @StateObject private var locationManager = LocationManager.shared

    @State private var position: MapCameraPosition = .region(
        MKCoordinateRegion(
            center: CLLocationCoordinate2D(latitude: 4.65, longitude: -74.05),
            span: MKCoordinateSpan(latitudeDelta: 12.0, longitudeDelta: 12.0)
        )
    )

    @State private var showSettings = false
    @State private var showFeltReport = false
    @State private var showDamageReport = false
    @State private var isSheetPresented = true

    public init() {}

    public var body: some View {
        ZStack(alignment: .top) {
            // Mapa nativo de Apple a pantalla completa
            Map(position: $position) {
                // Anotación de Ubicación del Usuario
                UserAnnotation()

                // Anotaciones de Sismos
                ForEach(state.events) { event in
                    if let coord = event.coordinate {
                        Annotation(
                            event.place ?? "Sismo",
                            coordinate: coord
                        ) {
                            Button {
                                state.selectEvent(event)
                            } label: {
                                MagnitudeBadge(
                                    magnitude: event.magnitude,
                                    isPreliminary: event.isPreliminary,
                                    fontSize: 13
                                )
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }

                // Estaciones sismológicas
                ForEach(state.stations) { station in
                    Annotation(
                        station.id,
                        coordinate: station.coordinate
                    ) {
                        Circle()
                            .fill(SeismikColors.glacier.opacity(0.85))
                            .frame(width: 8, height: 8)
                            .overlay {
                                Circle()
                                    .stroke(Color.white, lineWidth: 1.2)
                            }
                    }
                }
            }
            .mapStyle(.standard(elevation: .realistic, pointsOfInterest: .excludingAll))
            .mapControls {
                MapCompass()
                MapScaleView()
            }
            .ignoresSafeArea()

            // Cápsula Flotante de Identidad y Estado de Red
            FloatingHeaderView(state: state, showSettings: $showSettings)
                .safeAreaInset(edge: .top) { Color.clear.frame(height: 0) }

            // Botón flotante para recentrar en la ubicación del usuario
            VStack {
                Spacer()
                HStack {
                    Spacer()
                    Button {
                        HapticManager.light()
                        if let userCoord = locationManager.userCoordinate {
                            withAnimation(.easeInOut(duration: 0.6)) {
                                position = .region(
                                    MKCoordinateRegion(
                                        center: userCoord,
                                        span: MKCoordinateSpan(latitudeDelta: 3.5, longitudeDelta: 3.5)
                                    )
                                )
                            }
                        } else {
                            locationManager.requestPermission()
                        }
                    } label: {
                        Image(systemName: "location.fill")
                            .font(.system(size: 16, weight: .semibold))
                            .foregroundColor(SeismikColors.systemBlue)
                            .frame(width: 44, height: 44)
                            .background(.ultraThinMaterial, in: Circle())
                            .overlay {
                                Circle().strokeBorder(Color.white.opacity(0.6), lineWidth: 0.8)
                            }
                            .shadow(color: Color.black.opacity(0.15), radius: 8, x: 0, y: 4)
                    }
                    .buttonStyle(.plain)
                    .padding(.trailing, 18)
                    .padding(.bottom, 160) // Evita solaparse con la hoja colapsada
                }
            }
        }
        // Hoja nativa interactiva con detents de resortes
        .sheet(isPresented: $isSheetPresented) {
            SeismicSheetView(
                state: state,
                locationManager: locationManager,
                showFeltReport: $showFeltReport,
                showDamageReport: $showDamageReport
            )
            .presentationDetents([.fraction(0.18), .medium, .large])
            .presentationDragIndicator(.visible)
            .presentationBackgroundInteraction(.enabled(upThrough: .medium))
            .interactiveDismissDisabled()
        }
        // Hoja de Detalle de Sismo Seleccionado
        .sheet(item: $state.selectedEvent) { event in
            EventDetailView(event: event)
        }
        // Modal de Configuración
        .sheet(isPresented: $showSettings) {
            SettingsView(state: state)
        }
        // Modal de Reporte "¿Lo sentiste?"
        .sheet(isPresented: $showFeltReport) {
            FeltReportView(preselectedEvent: state.events.first)
        }
        // Modal de Reporte de Daños
        .sheet(isPresented: $showDamageReport) {
            DamageReportView(preselectedEvent: state.events.first)
        }
        // Superposición de Alerta de Emergencia Crítica
        .overlay {
            if let alertEvent = state.activeAlert {
                EmergencyAlertView(event: alertEvent) {
                    state.dismissAlert()
                }
                .transition(.opacity.combined(with: .scale(scale: 0.96)))
            }
        }
    }
}
