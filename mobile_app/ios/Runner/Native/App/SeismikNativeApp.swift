import SwiftUI

/// Raíz de la aplicación nativa en SwiftUI de Seismik para iPhone.
public struct SeismikNativeAppRoot: View {
    public init() {}

    public var body: some View {
        MonitorView()
            .tint(SeismikColors.systemBlue)
    }
}
