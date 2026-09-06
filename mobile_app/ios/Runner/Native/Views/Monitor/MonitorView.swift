import SwiftUI
import MapKit

/// Vista principal de monitoreo con Apple MapKit interactivo a pantalla completa y hoja de sismos nativa.
public struct MonitorView: View {
    @StateObject private var state = SeismikState.shared
    @StateObject private var locationManager = LocationManager.shared

    @State private var targetRegion: MKCoordinateRegion?
    @State private var showSettings = false
    @State private var showFeltReport = false
    @State private var showDamageReport = false
    @State private var isSheetPresented = true

    public init() {}

    public var body: some View {
        ZStack(alignment: .top) {
            // Mapa nativo de Apple a pantalla completa
            NativeMapView(
                state: state,
                targetRegion: $targetRegion
            ) { selectedEvent in
                state.selectEvent(selectedEvent)
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
                            targetRegion = MKCoordinateRegion(
                                center: userCoord,
                                span: MKCoordinateSpan(latitudeDelta: 3.5, longitudeDelta: 3.5)
                            )
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
            .seismicSheetPresentation()
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

// MARK: - Mapa Nativo de Apple Compatible (iOS 15 - iOS 18+)
private struct NativeMapView: UIViewRepresentable {
    @ObservedObject var state: SeismikState
    @Binding var targetRegion: MKCoordinateRegion?
    let onSelectEvent: (SeismicEvent) -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(self)
    }

    func makeUIView(context: Context) -> MKMapView {
        let mapView = MKMapView()
        mapView.delegate = context.coordinator
        mapView.showsUserLocation = true
        mapView.showsCompass = true
        mapView.showsScale = true

        let defaultRegion = MKCoordinateRegion(
            center: CLLocationCoordinate2D(latitude: 4.65, longitude: -74.05),
            span: MKCoordinateSpan(latitudeDelta: 12.0, longitudeDelta: 12.0)
        )
        mapView.setRegion(defaultRegion, animated: false)

        return mapView
    }

    func updateUIView(_ mapView: MKMapView, context: Context) {
        if let target = targetRegion {
            mapView.setRegion(target, animated: true)
            DispatchQueue.main.async {
                self.targetRegion = nil
            }
        }

        context.coordinator.syncAnnotations(mapView: mapView, events: state.events, stations: state.stations)
    }

    class Coordinator: NSObject, MKMapViewDelegate {
        var parent: NativeMapView
        private var lastEventIds: [String] = []
        private var lastStationIds: [String] = []

        init(_ parent: NativeMapView) {
            self.parent = parent
        }

        func syncAnnotations(mapView: MKMapView, events: [SeismicEvent], stations: [SeismicStation]) {
            let eventIds = events.map(\.id)
            let stationIds = stations.map(\.id)

            guard eventIds != lastEventIds || stationIds != lastStationIds else { return }
            lastEventIds = eventIds
            lastStationIds = stationIds

            let current = mapView.annotations.filter { !($0 is MKUserLocation) }
            mapView.removeAnnotations(current)

            var newAnnotations: [MKAnnotation] = []

            for event in events {
                if let coord = event.coordinate {
                    newAnnotations.append(SeismicPointAnnotation(event: event, coordinate: coord))
                }
            }

            for station in stations {
                newAnnotations.append(StationPointAnnotation(station: station))
            }

            mapView.addAnnotations(newAnnotations)
        }

        func mapView(_ mapView: MKMapView, viewFor annotation: MKAnnotation) -> MKAnnotationView? {
            if annotation is MKUserLocation {
                return nil // Punto de ubicación nativo de Apple
            }

            if let seismic = annotation as? SeismicPointAnnotation {
                let identifier = "SeismicBadgeAnnotation"
                var annotationView = mapView.dequeueReusableAnnotationView(withIdentifier: identifier)
                if annotationView == nil {
                    annotationView = MKAnnotationView(annotation: annotation, reuseIdentifier: identifier)
                    annotationView?.canShowCallout = false
                } else {
                    annotationView?.annotation = annotation
                }

                if let aView = annotationView {
                    configureBadgeView(annotationView: aView, event: seismic.event)
                }
                return annotationView
            }

            if annotation is StationPointAnnotation {
                let identifier = "StationDotAnnotation"
                var annotationView = mapView.dequeueReusableAnnotationView(withIdentifier: identifier)
                if annotationView == nil {
                    annotationView = MKAnnotationView(annotation: annotation, reuseIdentifier: identifier)
                    annotationView?.canShowCallout = true
                    let dot = UIView(frame: CGRect(x: 0, y: 0, width: 8, height: 8))
                    dot.backgroundColor = UIColor(red: 0.22, green: 0.74, blue: 0.96, alpha: 0.85)
                    dot.layer.cornerRadius = 4
                    dot.layer.borderWidth = 1.2
                    dot.layer.borderColor = UIColor.white.cgColor
                    annotationView?.addSubview(dot)
                    annotationView?.frame = CGRect(x: 0, y: 0, width: 8, height: 8)
                } else {
                    annotationView?.annotation = annotation
                }
                return annotationView
            }

            return nil
        }

        private func configureBadgeView(annotationView: MKAnnotationView, event: SeismicEvent) {
            annotationView.subviews.forEach { $0.removeFromSuperview() }

            let badge = MagnitudeBadge(
                magnitude: event.magnitude,
                isPreliminary: event.isPreliminary,
                fontSize: 13
            )
            let hostingController = UIHostingController(rootView: badge)
            guard let badgeView = hostingController.view else { return }
            badgeView.backgroundColor = .clear
            badgeView.translatesAutoresizingMaskIntoConstraints = false
            badgeView.isUserInteractionEnabled = false

            annotationView.addSubview(badgeView)
            NSLayoutConstraint.activate([
                badgeView.centerXAnchor.constraint(equalTo: annotationView.centerXAnchor),
                badgeView.centerYAnchor.constraint(equalTo: annotationView.centerYAnchor),
            ])
            annotationView.frame = CGRect(x: 0, y: 0, width: 44, height: 36)
        }

        func mapView(_ mapView: MKMapView, didSelect view: MKAnnotationView) {
            if let seismic = view.annotation as? SeismicPointAnnotation {
                HapticManager.light()
                parent.onSelectEvent(seismic.event)
                mapView.deselectAnnotation(seismic, animated: false)
            }
        }
    }
}

// MARK: - Modelos de Anotación MapKit
private class SeismicPointAnnotation: NSObject, MKAnnotation {
    let event: SeismicEvent
    dynamic var coordinate: CLLocationCoordinate2D

    init(event: SeismicEvent, coordinate: CLLocationCoordinate2D) {
        self.event = event
        self.coordinate = coordinate
        super.init()
    }

    var title: String? { event.place ?? "Sismo" }
}

private class StationPointAnnotation: NSObject, MKAnnotation {
    let station: SeismicStation
    dynamic var coordinate: CLLocationCoordinate2D

    init(station: SeismicStation) {
        self.station = station
        self.coordinate = station.coordinate
        super.init()
    }

    var title: String? { "Estación \(station.id)" }
}

