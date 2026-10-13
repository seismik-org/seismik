import Flutter
import FirebaseAppCheck
import FirebaseCore
import UIKit
import UserNotifications
import SwiftUI

@main
@objc class AppDelegate: FlutterAppDelegate {

  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    // Hosted unit tests exercise pure models and contracts, not live APNs,
    // App Check, motion sensors or account services. SceneDelegate applies the
    // same check: with scenes, it is the one that mounts the SwiftUI app.
    if SeismikLaunchEnvironment.isHostingUnitTests {
      let testWindow = UIWindow(frame: UIScreen.main.bounds)
      testWindow.rootViewController = UIViewController()
      window = testWindow
      testWindow.makeKeyAndVisible()
      return true
    }
    // La interfaz es SwiftUI nativa, por lo que no hay un `Firebase.initializeApp`
    // de Dart que configure App Check por nosotros. El proveedor debe instalarse
    // antes de crear la app Firebase para que el primer registro sea verificable.
    // A missing configuration must not abort the process. Registration retries
    // the same preparation and reports a configuration error, not a signal error.
    try? SeismikFirebaseRuntime.prepare()

    GeneratedPluginRegistrant.register(with: self)
    let launched = super.application(application, didFinishLaunchingWithOptions: launchOptions)

    if let notification = launchOptions?[.remoteNotification] as? [AnyHashable: Any] {
      Task { @MainActor in
        SeismikState.shared.handleRemoteNotification(notification, opened: true)
      }
    }

    // Registrar APNs no muestra un permiso. El permiso de presentación (con las
    // alertas críticas) lo pide la bienvenida del primer arranque
    // (PermissionsOnboardingView) y, después, Configuración: sin él los avisos
    // y los simulacros llegan al teléfono pero iOS no los muestra.
    UNUserNotificationCenter.current().delegate = SeismikNotificationPresenter.shared
    application.registerForRemoteNotifications()

    // Doble garantía: asegura que la ventana principal muestre directamente
    // la app nativa en SwiftUI (SeismikNativeAppRoot) y jamás el FlutterViewController.
    let appWindow = self.window ?? UIWindow(frame: UIScreen.main.bounds)
    appWindow.rootViewController = UIHostingController(rootView: SeismikNativeAppRoot())
    self.window = appWindow
    appWindow.makeKeyAndVisible()

    return launched
  }

  override func application(
    _ application: UIApplication,
    didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data
  ) {
    super.application(application, didRegisterForRemoteNotificationsWithDeviceToken: deviceToken)
    let tokenHex = deviceToken.map { String(format: "%02.2hhx", $0) }.joined()
    UserDefaults.standard.set(tokenHex, forKey: "seismik.apns_device_token")
    Task { @MainActor in
      await SeismikState.shared.updateRegistration()
    }
  }

  override func application(
    _ application: UIApplication,
    didReceiveRemoteNotification userInfo: [AnyHashable: Any],
    fetchCompletionHandler completionHandler: @escaping (UIBackgroundFetchResult) -> Void
  ) {
    Task { @MainActor in
      SeismikState.shared.handleRemoteNotification(userInfo)
      await SeismikState.shared.syncMissedAlerts()
      completionHandler(.newData)
    }
  }
}

/// El simulador de CI lanza la app como anfitriona de XCTest con un
/// GoogleService-Info.plist de relleno: configurar Firebase aborta
/// (FirebaseInstallations rechaza la clave) y montar la interfaz real llama a
/// App Check sin Firebase. En ese caso la app no arranca nada de eso.
enum SeismikLaunchEnvironment {
  static var isHostingUnitTests: Bool {
    #if DEBUG
    return ProcessInfo.processInfo.environment["XCTestConfigurationFilePath"] != nil
      || NSClassFromString("XCTestCase") != nil
    #else
    return false
    #endif
  }
}

enum SeismikFirebaseRuntime {
  private static let lock = NSLock()
  private static let provider = SeismikAppCheckProviderFactory()

  static func prepare() throws {
    lock.lock()
    defer { lock.unlock() }
    if FirebaseApp.app() != nil { return }
    guard !SeismikLaunchEnvironment.isHostingUnitTests,
          let path = Bundle.main.path(forResource: "GoogleService-Info", ofType: "plist"),
          let options = FirebaseOptions(contentsOfFile: path) else {
      throw SeismikAPIError.rejected(status: 503, message: "La configuración de verificación de esta versión no está disponible. Actualiza Seismik; no es un fallo de señal.")
    }
    AppCheck.setAppCheckProviderFactory(provider)
    FirebaseApp.configure(options: options)
  }
}

/// DeviceCheck funciona desde iOS 11 y no exige una capacidad adicional en el
/// perfil de distribución. Firebase entrega al backend un token App Check real.
/// Si no lo consigue, el registro envía un marcador no verificado que el
/// servidor rechaza en cuanto exige App Check (SeismikAPIClient.registerDevice).
private final class SeismikAppCheckProviderFactory: NSObject, AppCheckProviderFactory {
  func createProvider(with app: FirebaseApp) -> AppCheckProvider? {
    DeviceCheckProvider(app: app)
  }
}
