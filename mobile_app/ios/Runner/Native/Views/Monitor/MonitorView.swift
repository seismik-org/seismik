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
    @State private var drawerPosition: DrawerPosition = .peek
    @State private var drawerTranslation: CGFloat = 0
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    public init() {}

    public var body: some View {
        GeometryReader { geometry in
            let expandedHeight = max(geometry.size.height - geometry.safeAreaInsets.top - 12, 420)
            let visibleHeight = drawerPosition.height(in: geometry.size.height)
            let baseOffset = expandedHeight - visibleHeight
            let drawerOffset = min(
                max(baseOffset + drawerTranslation, 0),
                expandedHeight - DrawerPosition.peek.height(in: geometry.size.height)
            )

            ZStack(alignment: .top) {
                NativeMapView(
                    state: state,
                    targetRegion: $targetRegion,
                    coveredBottomInset: visibleHeight
                ) { selectedEvent in
                    state.selectEvent(selectedEvent)
                }
                .ignoresSafeArea()

                FloatingHeaderView(state: state, showSettings: $showSettings)
                    .padding(.top, max(8, geometry.safeAreaInsets.top + 4))

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
                                .frame(width: 44, height: 44)
                                .liquidGlass(cornerRadius: 22)
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel("Centrar mapa en mi ubicación")
                        .padding(.trailing, 18)
                        .padding(.bottom, DrawerPosition.peek.height(in: geometry.size.height) + 16)
                    }
                }

                SeismicSheetView(
                    state: state,
                    locationManager: locationManager,
                    showFeltReport: $showFeltReport,
                    showDamageReport: $showDamageReport,
                    onDrawerDragChanged: { drawerTranslation = $0 },
                    onDrawerDragEnded: { projectedTranslation in
                        settleDrawer(
                            projectedTranslation: projectedTranslation,
                            expandedHeight: expandedHeight,
                            screenHeight: geometry.size.height
                        )
                    },
                    onDrawerHandleTapped: cycleDrawer
                )
                .frame(height: expandedHeight)
                .offset(y: drawerOffset)
                .frame(maxHeight: .infinity, alignment: .bottom)
                .animation(
                    reduceMotion ? .easeOut(duration: 0.18) : .spring(response: 0.35, dampingFraction: 0.86),
                    value: drawerPosition
                )
            }
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

    private func settleDrawer(
        projectedTranslation: CGFloat,
        expandedHeight: CGFloat,
        screenHeight: CGFloat
    ) {
        let projectedOffset = expandedHeight
            - drawerPosition.height(in: screenHeight)
            + projectedTranslation
        let next = DrawerPosition.allCases.min {
            abs(expandedHeight - $0.height(in: screenHeight) - projectedOffset)
                < abs(expandedHeight - $1.height(in: screenHeight) - projectedOffset)
        } ?? .medium
        withAnimation(drawerAnimation) {
            drawerTranslation = 0
            drawerPosition = next
        }
        HapticManager.selection()
    }

    private func cycleDrawer() {
        withAnimation(drawerAnimation) {
            switch drawerPosition {
            case .peek: drawerPosition = .medium
            case .medium: drawerPosition = .expanded
            case .expanded: drawerPosition = .peek
            }
        }
        HapticManager.selection()
    }

    private var drawerAnimation: Animation {
        reduceMotion ? .easeOut(duration: 0.18) : .spring(response: 0.35, dampingFraction: 0.86)
    }
}

private enum DrawerPosition: CaseIterable {
    case peek
    case medium
    case expanded

    func height(in screenHeight: CGFloat) -> CGFloat {
        switch self {
        case .peek: return 138
        case .medium: return max(310, screenHeight * 0.45)
        case .expanded: return max(420, screenHeight * 0.85)
        }
    }
}

// MARK: - Mapa Nativo de Apple Compatible (iOS 15 - iOS 18+)
private struct NativeMapView: UIViewRepresentable {
    @ObservedObject var state: SeismikState
    @Binding var targetRegion: MKCoordinateRegion?
    let coveredBottomInset: CGFloat
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
        mapView.pointOfInterestFilter = .excludingAll

        let defaultRegion = MKCoordinateRegion(
            center: CLLocationCoordinate2D(latitude: 4.65, longitude: -74.05),
            span: MKCoordinateSpan(latitudeDelta: 12.0, longitudeDelta: 12.0)
        )
        mapView.setRegion(defaultRegion, animated: false)

        return mapView
    }

    func updateUIView(_ mapView: MKMapView, context: Context) {
        let targetType: MKMapType
        switch state.appMapType {
        case "satellite": targetType = .satellite
        case "hybrid": targetType = .hybrid
        default: targetType = .standard
        }
        if mapView.mapType != targetType {
            mapView.mapType = targetType
        }

        mapView.layoutMargins = UIEdgeInsets(
            top: 96,
            left: 12,
            bottom: max(coveredBottomInset + 10, 148),
            right: 12
        )
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
        private var lastEventSnapshots: [String] = []
        private var lastStationSnapshots: [String] = []

        init(_ parent: NativeMapView) {
            self.parent = parent
        }

        func syncAnnotations(mapView: MKMapView, events: [SeismicEvent], stations: [SeismicStation]) {
            let eventSnapshots = events.map {
                "\($0.id)|\($0.magnitude ?? -1)|\($0.latitude ?? 999)|\($0.longitude ?? 999)|\($0.isPreliminary)"
            }
            let stationSnapshots = stations.map {
                "\($0.id)|\($0.latitude)|\($0.longitude)"
            }

            guard eventSnapshots != lastEventSnapshots || stationSnapshots != lastStationSnapshots else { return }
            lastEventSnapshots = eventSnapshots
            lastStationSnapshots = stationSnapshots

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
                let annotationView = mapView.dequeueReusableAnnotationView(
                    withIdentifier: identifier
                ) as? MagnitudeAnnotationView
                    ?? MagnitudeAnnotationView(annotation: annotation, reuseIdentifier: identifier)
                annotationView.annotation = annotation
                annotationView.configure(with: seismic.event)
                annotationView.clusteringIdentifier = "seismik-events"
                return annotationView
            }

            if let cluster = annotation as? MKClusterAnnotation {
                let identifier = "SeismicClusterAnnotation"
                let marker = mapView.dequeueReusableAnnotationView(
                    withIdentifier: identifier
                ) as? MKMarkerAnnotationView
                    ?? MKMarkerAnnotationView(annotation: cluster, reuseIdentifier: identifier)
                marker.annotation = cluster
                marker.markerTintColor = UIColor.systemIndigo
                marker.glyphText = "\(cluster.memberAnnotations.count)"
                marker.titleVisibility = .hidden
                marker.subtitleVisibility = .hidden
                marker.displayPriority = .defaultHigh
                marker.accessibilityLabel = "\(cluster.memberAnnotations.count) sismos agrupados"
                return marker
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

        func mapView(_ mapView: MKMapView, didSelect view: MKAnnotationView) {
            if let seismic = view.annotation as? SeismicPointAnnotation {
                HapticManager.light()
                parent.onSelectEvent(seismic.event)
            }
        }
    }
}

private final class MagnitudeAnnotationView: MKAnnotationView {
    private let magnitudeLabel = UILabel()

    override init(annotation: MKAnnotation?, reuseIdentifier: String?) {
        super.init(annotation: annotation, reuseIdentifier: reuseIdentifier)
        bounds = CGRect(x: 0, y: 0, width: 48, height: 32)
        centerOffset = CGPoint(x: 0, y: -18)
        canShowCallout = false
        collisionMode = .rectangle
        displayPriority = .required
        layer.cornerRadius = 12
        layer.cornerCurve = .continuous
        layer.borderWidth = 1
        layer.borderColor = UIColor.white.withAlphaComponent(0.8).cgColor
        layer.shadowColor = UIColor.black.cgColor
        layer.shadowOpacity = 0.22
        layer.shadowRadius = 4
        layer.shadowOffset = CGSize(width: 0, height: 2)

        magnitudeLabel.translatesAutoresizingMaskIntoConstraints = false
        magnitudeLabel.textAlignment = .center
        magnitudeLabel.textColor = .white
        magnitudeLabel.font = .rounded(ofSize: 14, weight: .bold)
        magnitudeLabel.adjustsFontSizeToFitWidth = true
        magnitudeLabel.minimumScaleFactor = 0.8
        addSubview(magnitudeLabel)
        NSLayoutConstraint.activate([
            magnitudeLabel.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 4),
            magnitudeLabel.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -4),
            magnitudeLabel.topAnchor.constraint(equalTo: topAnchor),
            magnitudeLabel.bottomAnchor.constraint(equalTo: bottomAnchor)
        ])
        isAccessibilityElement = true
        accessibilityTraits = .button
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    func configure(with event: SeismicEvent) {
        if event.isPreliminary && event.magnitude == nil {
            magnitudeLabel.text = "P"
            backgroundColor = UIColor.systemPurple
            accessibilityLabel = "Sismo preliminar, magnitud pendiente"
            return
        }
        let magnitude = event.magnitude
        magnitudeLabel.text = magnitude.map { String(format: "%.1f", $0) } ?? "—"
        switch magnitude ?? 0 {
        case ..<3.0: backgroundColor = UIColor.systemGreen
        case ..<5.0: backgroundColor = UIColor(red: 0.78, green: 0.47, blue: 0.03, alpha: 1)
        case ..<6.5: backgroundColor = UIColor.systemOrange
        default: backgroundColor = UIColor.systemRed
        }
        accessibilityLabel = magnitude.map { "Sismo de magnitud \(String(format: "%.1f", $0))" }
            ?? "Sismo con magnitud pendiente"
        accessibilityHint = "Abre el detalle del sismo"
    }

    override func setSelected(_ selected: Bool, animated: Bool) {
        super.setSelected(selected, animated: animated)
        let changes = {
            self.transform = selected ? CGAffineTransform(scaleX: 1.18, y: 1.18) : .identity
            self.layer.borderWidth = selected ? 2.5 : 1
        }
        if animated {
            UIView.animate(withDuration: 0.18, animations: changes)
        } else {
            changes()
        }
        accessibilityTraits = selected ? [.button, .selected] : .button
    }

    override func prepareForReuse() {
        super.prepareForReuse()
        transform = .identity
        layer.borderWidth = 1
    }
}

private extension UIFont {
    static func rounded(ofSize size: CGFloat, weight: UIFont.Weight) -> UIFont {
        let base = UIFont.systemFont(ofSize: size, weight: weight)
        guard let descriptor = base.fontDescriptor.withDesign(.rounded) else { return base }
        return UIFont(descriptor: descriptor, size: size)
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
