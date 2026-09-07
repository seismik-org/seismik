import SafariServices
import SwiftUI

/// Navegador del sistema integrado en la app. Conserva controles de Safari,
/// privacidad y llavero sin expulsar a la persona de Seismik.
public struct InAppBrowserView: UIViewControllerRepresentable {
    public let url: URL

    public init(url: URL) {
        self.url = url
    }

    public func makeUIViewController(context: Context) -> SFSafariViewController {
        let controller = SFSafariViewController(url: url)
        controller.preferredControlTintColor = UIColor.systemBlue
        controller.dismissButtonStyle = .close
        return controller
    }

    public func updateUIViewController(
        _ uiViewController: SFSafariViewController,
        context: Context
    ) {}
}

public struct BrowserDestination: Identifiable {
    public let id = UUID()
    public let url: URL

    public init(url: URL) {
        self.url = url
    }
}
