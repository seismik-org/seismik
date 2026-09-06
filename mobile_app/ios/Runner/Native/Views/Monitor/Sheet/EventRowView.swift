import SwiftUI

/// Fila de evento sísmico en tarjeta de cristal con retroalimentación táctil y chevron nativo.
public struct EventRowView: View {
    public let event: SeismicEvent
    public let userDistanceKm: Double?
    public let onSelect: () -> Void

    public var body: some View {
        Button(action: onSelect) {
            HStack(spacing: 14) {
                // Insignia de Magnitud con acabado joya
                MagnitudeBadge(
                    magnitude: event.magnitude,
                    isPreliminary: event.isPreliminary,
                    fontSize: 16
                )

                // Datos descriptivos
                VStack(alignment: .leading, spacing: 3) {
                    Text(event.place ?? "Evento sísmico")
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundColor(.primary)
                        .lineLimit(1)

                    HStack(spacing: 6) {
                        Text(event.agencyDisplayName)
                        Text("·")
                        Text(event.relativeTimeFormatted)

                        if let depth = event.depthKm {
                            Text("·")
                            Text("\(Int(depth)) km")
                        }

                        if let dist = userDistanceKm {
                            Text("·")
                            Text("a \(Int(dist)) km")
                                .foregroundColor(SeismikColors.glacier)
                        }
                    }
                    .font(.system(size: 12.5, weight: .regular))
                    .foregroundColor(.secondary)
                    .lineLimit(1)
                }

                Spacer()

                // Indicador de navegación nativo
                Image(systemName: "chevron.right")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(Color.secondary.opacity(0.7))
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 12)
            .liquidGlass(cornerRadius: 18, showShadow: false)
        }
        .buttonStyle(.plain)
    }
}
