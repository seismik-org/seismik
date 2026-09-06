import Flutter
import GoogleMaps
import UIKit
import SwiftUI

@main
@objc class AppDelegate: FlutterAppDelegate {
  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    if let mapsKey = Bundle.main.object(forInfoDictionaryKey: "SeismikGoogleMapsAPIKey") as? String,
       !mapsKey.isEmpty,
       !mapsKey.hasPrefix("$(") {
      GMSServices.provideAPIKey(mapsKey)
    }
    GeneratedPluginRegistrant.register(with: self)
    let launched = super.application(application, didFinishLaunchingWithOptions: launchOptions)

    // Solicita registro ante APNs de Apple para recepción de alertas sísmicas
    application.registerForRemoteNotifications()

    // Despliega la experiencia nativa de Apple en SwiftUI y Liquid Glass
    let nativeWindow = UIWindow(frame: UIScreen.main.bounds)
    let hostingController = UIHostingController(rootView: SeismikNativeAppRoot())
    nativeWindow.rootViewController = hostingController
    self.window = nativeWindow
    nativeWindow.makeKeyAndVisible()

    return launched
  }

  override func application(
    _ application: UIApplication,
    didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data
  ) {
    super.application(application, didRegisterForRemoteNotificationsWithDeviceToken: deviceToken)
    let tokenHex = deviceToken.map { String(format: "%02.2hhx", $0) }.joined()
    UserDefaults.standard.set(tokenHex, forKey: "seismik.apns_device_token")
    Task {
      await SeismikState.shared.updateRegistration()
    }
  }
}

