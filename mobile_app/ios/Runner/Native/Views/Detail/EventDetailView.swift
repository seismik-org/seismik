import SwiftUI
import MapKit

/// Vista detallada del reporte sísmico con hero de magnitud, métricas y mapa satelital del epicentro.
public struct EventDetailView: View {
    public let event: SeismicEvent
    @Environment(\.dismiss) private var dismiss
    @AppStorage("seismik.map_provider") private var mapProvider = "apple"

    public var body: some View {
        CompatibleNavigationStack {
            ScrollView {
                VStack(spacing: 20) {
                    // Hero de Magnitud Monumental
                    VStack(spacing: 8) {
                        Text(event.magnitude.map { String(format: "%.1f", $0) } ?? "—")
                            .font(.system(size: 72, weight: .bold, design: .rounded))
                            .foregroundColor(.white)
                            .shadow(
                                color: SeismikColors.severityColor(for: event.magnitude).opacity(0.4),
                                radius: 16,
                                y: 6
                            )

                        Text("MAGNITUD REGISTRADA")
                            .font(.system(size: 11, weight: .bold, design: .rounded))
                            .tracking(2.0)
                            .foregroundColor(.white.opacity(0.85))

                        Text(event.place ?? "Epicentro no determinado")
                            .font(.system(size: 18, weight: .semibold))
                            .foregroundColor(.white)
                            .multilineTextAlignment(.center)
                            .padding(.horizontal, 20)
                            .padding(.top, 4)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 32)
                    .background {
                        RoundedRectangle(cornerRadius: 26, style: .continuous)
                            .fill(SeismikColors.severityGradient(for: event.magnitude, isPreliminary: event.isPreliminary))
                    }
                    .overlay {
                        RoundedRectangle(cornerRadius: 26, style: .continuous)
                            .strokeBorder(Color.white.opacity(0.4), lineWidth: 0.8)
                    }
                    .shadow(color: Color.black.opacity(0.12), radius: 16, y: 8)
                    .padding(.horizontal, 16)

                    // Alerta de Tsunami si aplica
                    if event.tsunamiWarning {
                        HStack(spacing: 12) {
                            Image(systemName: "water.waves.and.arrow.up")
                                .font(.system(size: 22, weight: .bold))
                                .foregroundColor(SeismikColors.crimson)
                            VStack(alignment: .leading, spacing: 2) {
                                Text("ALERTA DE TSUNAMI EMITIDA")
                                    .font(.system(size: 13, weight: .bold))
                                    .foregroundColor(SeismikColors.crimson)
                                Text("Evacúe inmediatamente zonas costeras bajas.")
                                    .font(.system(size: 12))
                                    .foregroundColor(.secondary)
                            }
                            Spacer()
                        }
                        .padding(14)
                        .liquidGlass(cornerRadius: 18, tint: SeismikColors.crimson)
                        .padding(.horizontal, 16)
                    }

                    // Cuadrícula de Métricas Clave
                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
                        MetricCard(
                            title: "PROFUNDIDAD",
                            value: event.depthKm.map { "\(Int($0)) km" } ?? "No disponible",
                            icon: "arrow.down.to.line.compact"
                        )
                        MetricCard(
                            title: "ENTIDAD",
                            value: event.agencyDisplayName,
                            icon: "building.columns"
                        )
                        MetricCard(
                            title: "HORA DETECCIÓN",
                            value: event.relativeTimeFormatted,
                            icon: "clock"
                        )
                        MetricCard(
                            title: "TIPO",
                            value: event.isPreliminary ? "Preliminar" : "Oficial",
                            icon: "checkmark.seal"
                        )
                    }
                    .padding(.horizontal, 16)

                    // Mini Mapa del Epicentro
                    if let coord = event.coordinate {
                        VStack(alignment: .leading, spacing: 10) {
                            Text("LOCALIZACIÓN DEL EPICENTRO")
                                .font(.system(size: 11, weight: .bold))
                                .tracking(1.4)
                                .foregroundColor(.secondary)
                                .padding(.horizontal, 4)

                            EpicenterMapView(coordinate: coord, title: event.place)
                            .frame(height: 180)
                            .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
                            .overlay {
                                RoundedRectangle(cornerRadius: 20, style: .continuous)
                                    .strokeBorder(Color.white.opacity(0.3), lineWidth: 0.8)
                            }

                            // El proveedor se elige en Ajustes; el mapa principal siempre usa MapKit.
                            Button {
                                HapticManager.light()
                                openEpicenter(coord)
                            } label: {
                                HStack {
                                    Image(systemName: "map.fill")
                                    Text(mapProvider == "google" ? "Abrir en Google Maps" : "Abrir en Apple Maps")
                                        .font(.system(size: 15, weight: .semibold))
                                }
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 14)
                                .liquidGlass(cornerRadius: 16)
                            }
                            .buttonStyle(.plain)
                        }
                        .padding(.horizontal, 16)
                    }

                    // Pasos de Seguridad
                    VStack(alignment: .leading, spacing: 10) {
                        Text("DURANTE UN SISMO")
                            .font(.system(size: 11, weight: .bold))
                            .tracking(1.4)
                            .foregroundColor(.secondary)
                            .padding(.horizontal, 4)

                        HStack(spacing: 10) {
                            SafetyStepCard(number: "1", title: "Agáchate", subtitle: "Antes de caer")
                            SafetyStepCard(number: "2", title: "Cúbrete", subtitle: "Bajo una mesa")
                            SafetyStepCard(number: "3", title: "Sujétate", subtitle: "Hasta que pare")
                        }
                    }
                    .padding(.horizontal, 16)
                    .padding(.bottom, 30)
                }
                .padding(.top, 16)
            }
            .navigationTitle("Detalle del Sismo")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button {
                        HapticManager.selection()
                        dismiss()
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .font(.system(size: 24))
                            .symbolRenderingMode(.hierarchical)
                            .foregroundColor(.secondary)
                    }
                }
            }
        }
        .modalSheetPresentation()
    }

    private func openEpicenter(_ coordinate: CLLocationCoordinate2D) {
        if mapProvider == "google" {
            let query = "\(coordinate.latitude),\(coordinate.longitude)"
            if let appURL = URL(string: "comgooglemaps://?q=\(query)&center=\(query)"),
               UIApplication.shared.canOpenURL(appURL) {
                UIApplication.shared.open(appURL)
                return
            }
            if let webURL = URL(string: "https://www.google.com/maps/search/?api=1&query=\(query)") {
                UIApplication.shared.open(webURL)
            }
            return
        }

        let placemark = MKPlacemark(coordinate: coordinate)
        let item = MKMapItem(placemark: placemark)
        item.name = "Epicentro: \(event.place ?? "Sismo")"
        item.openInMaps()
    }
}

// MARK: - Tarjeta de Métrica Auxiliar
private struct MetricCard: View {
    let title: String
    let value: String
    let icon: String

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                Image(systemName: icon)
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)
                Text(title)
                    .font(.system(size: 10.5, weight: .bold))
                    .tracking(1.0)
                    .foregroundColor(.secondary)
            }
            Text(value)
                .font(.system(size: 16, weight: .bold, design: .rounded))
                .foregroundColor(.primary)
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .liquidGlass(cornerRadius: 18)
    }
}

// MARK: - Tarjeta de Paso de Seguridad
private struct SafetyStepCard: View {
    let number: String
    let title: String
    let subtitle: String

    var body: some View {
        VStack(spacing: 4) {
            Text(number)
                .font(.system(size: 18, weight: .black, design: .rounded))
                .foregroundColor(SeismikColors.glacier)
            Text(title)
                .font(.system(size: 13, weight: .bold))
                .foregroundColor(.primary)
            Text(subtitle)
                .font(.system(size: 10))
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 12)
        .padding(.horizontal, 4)
        .liquidGlass(cornerRadius: 16)
    }
}

// MARK: - Mini Mapa del Epicentro Compatible (iOS 15+)
private struct EpicenterMapView: UIViewRepresentable {
    let coordinate: CLLocationCoordinate2D
    let title: String?

    func makeUIView(context: Context) -> MKMapView {
        let map = MKMapView()
        map.isScrollEnabled = false
        map.isZoomEnabled = false
        let region = MKCoordinateRegion(
            center: coordinate,
            span: MKCoordinateSpan(latitudeDelta: 1.2, longitudeDelta: 1.2)
        )
        map.setRegion(region, animated: false)
        let pin = MKPointAnnotation()
        pin.coordinate = coordinate
        pin.title = title
        map.addAnnotation(pin)
        return map
    }

    func updateUIView(_ uiView: MKMapView, context: Context) {}
}
