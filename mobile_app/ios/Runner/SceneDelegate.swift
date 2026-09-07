import Flutter
import UIKit
import SwiftUI

class SceneDelegate: FlutterSceneDelegate {
  override func scene(
    _ scene: UIScene,
    willConnectTo session: UISceneSession,
    options connectionOptions: UIScene.ConnectionOptions
  ) {
    super.scene(scene, willConnectTo: session, options: connectionOptions)
    // `FlutterSceneDelegate` ya conectó la UIWindow del storyboard. Reutilizarla
    // conserva correctamente el ciclo de vida de la escena y evita una ventana
    // huérfana superpuesta a la real.
    guard let windowScene = scene as? UIWindowScene else { return }
    let appWindow = self.window ?? UIWindow(windowScene: windowScene)
    appWindow.rootViewController = UIHostingController(rootView: SeismikNativeAppRoot())
    self.window = appWindow
    appWindow.makeKeyAndVisible()
  }
}

