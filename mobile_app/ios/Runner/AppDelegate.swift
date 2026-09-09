import Flutter
import FirebaseAppCheck
import FirebaseCore
import GoogleMaps
import UIKit
import UserNotifications
import SwiftUI

@main
@objc class AppDelegate: FlutterAppDelegate {
  private let appCheckProviderFactory = SeismikAppCheckProviderFactory()

  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    // La interfaz es SwiftUI nativa, por lo que no hay un `Firebase.initializeApp`
    // de Dart que configure App Check por nosotros. El proveedor debe instalarse
    // antes de crear la app Firebase para que el primer registro sea verificable.
    AppCheck.setAppCheckProviderFactory(appCheckProviderFactory)
    if FirebaseApp.app() == nil {
      FirebaseApp.configure()
    }

    // La clave de Maps llega desde `SEISMIK_GOOGLE_MAPS_API_KEY`: el workflow de
    // TestFlight la inyecta desde un secreto y en local sale de Seismik.xcconfig.
    // No se escribe aquí ningún valor por defecto: este archivo va a un
    // repositorio público, y una clave escrita en el código la puede usar
    // cualquiera y facturártela a ti.
    let configuredKey = Bundle.main.object(forInfoDictionaryKey: "SeismikGoogleMapsAPIKey") as? String
    if let mapsKey = configuredKey, !mapsKey.isEmpty, !mapsKey.hasPrefix("$(") {
      GMSServices.provideAPIKey(mapsKey)
    } else {
      // El mapa principal es MapKit, así que la app arranca igual; sólo queda
      // sin servicio el SDK de Google Maps.
      NSLog("[Seismik] Falta SEISMIK_GOOGLE_MAPS_API_KEY; el SDK de Google Maps queda inactivo.")
    }
    GeneratedPluginRegistrant.register(with: self)
    let launched = super.application(application, didFinishLaunchingWithOptions: launchOptions)

    if let notification = launchOptions?[.remoteNotification] as? [AnyHashable: Any] {
      Task { @MainActor in
        SeismikState.shared.handleRemoteNotification(notification)
      }
    }

    // Sin autorización, iOS descarta el contenido de la alerta aunque APNs
    // entregue el push: el token llega igual, pero la persona no ve nada. Es
    // el permiso que hace útil a toda la app, así que se pide al arrancar.
    UNUserNotificationCenter.current().delegate = SeismikNotificationPresenter.shared
    UNUserNotificationCenter.current().requestAuthorization(
      options: [.alert, .sound, .badge]
    ) { _, _ in
      // El token de APNs sirve aunque la persona rechace: permite avisos
      // silenciosos y deja el dispositivo registrado para cuando cambie de
      // opinión desde Ajustes.
      DispatchQueue.main.async {
        application.registerForRemoteNotifications()
      }
    }

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

/// DeviceCheck funciona desde iOS 11 y no exige una capacidad adicional en el
/// perfil de distribución. Firebase entrega al backend un token App Check real;
/// no se envían marcadores de prueba en TestFlight.
private final class SeismikAppCheckProviderFactory: NSObject, AppCheckProviderFactory {
  func createProvider(with app: FirebaseApp) -> AppCheckProvider? {
    DeviceCheckProvider(app: app)
  }
}
