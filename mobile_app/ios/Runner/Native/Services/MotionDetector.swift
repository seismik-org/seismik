import CoreLocation
import CoreMotion
import Foundation
import UIKit

/// Constantes del procesamiento de señal compartidas con la app de Android.
///
/// Los umbrales viven en un solo lugar porque el backend exige diez
/// dispositivos únicos y cercanos para formar un candidato: si una plataforma
/// dispara con un criterio distinto, el quorum deja de ser comparable.
public enum SeismikDSP {
    public static let gravity: Double = 9.80665
    /// 0.04 g, el mismo umbral que usa el cliente Android.
    public static let shakeThreshold: Double = 0.04 * gravity
    public static let cooldown: TimeInterval = 3
    public static let window: TimeInterval = 2.5
    public static let maximumSamples = 160
    public static let userMotionVarianceThreshold: Double = 0.12
    /// Con menos muestras la varianza no describe nada; se trata como movimiento
    /// del usuario para no disparar durante los primeros instantes.
    public static let minimumSamplesForVariance = 12

    /// Varianza de la ventana previa al pico.
    ///
    /// Se calcula **antes** de añadir la muestra actual: incluir el propio
    /// impulso haría que un sismo real pareciera movimiento continuo.
    public static func variance(of values: [Double]) -> Double {
        guard values.count >= minimumSamplesForVariance else { return .infinity }
        let mean = values.reduce(0, +) / Double(values.count)
        let total = values.reduce(0) { $0 + pow($1 - mean, 2) }
        return total / Double(values.count)
    }

    /// Decide si una muestra merece enviarse como ping colaborativo.
    ///
    /// Cargando el teléfono suele estar quieto sobre una superficie, así que se
    /// admite el doble de varianza sin perder especificidad.
    public static func shouldReport(
        magnitude: Double,
        previousVariance: Double,
        isCharging: Bool,
        secondsSinceLastPing: TimeInterval
    ) -> Bool {
        let aboveThreshold = magnitude >= shakeThreshold
        let quietDevice = previousVariance <= userMotionVarianceThreshold
        let eligible = quietDevice
            || (isCharging && previousVariance <= userMotionVarianceThreshold * 2)
        return aboveThreshold && eligible && secondsSinceLastPing >= cooldown
    }
}

/// Detección colaborativa por acelerómetro.
///
/// Un teléfono nunca crea una alerta: sólo aporta un ping firmado que el backend
/// agrupa con los de otros dispositivos cercanos. Sin registro no se envía nada,
/// porque el ping va firmado con el secreto que entrega el alta.
public final class MotionDetector {
    public static let shared = MotionDetector()

    private let motion = CMMotionManager()
    private let api = SeismikAPIClient.shared
    private var samples: [(at: Date, magnitude: Double)] = []
    private var lastPing = Date.distantPast
    private var isSending = false
    private var isCharging = false

    public private(set) var isRunning = false

    private init() {}

    /// Empieza a escuchar el acelerómetro del usuario, sin gravedad.
    public func start() {
        guard !isRunning, motion.isDeviceMotionAvailable else { return }
        UIDevice.current.isBatteryMonitoringEnabled = true
        refreshCharging()
        isRunning = true
        // deviceMotion.userAcceleration ya excluye la gravedad, igual que el
        // `userAccelerometerEventStream` del cliente Android.
        motion.deviceMotionUpdateInterval = 1.0 / 50.0
        // El manejador llega en el hilo principal, que es donde vive todo el
        // estado mutable de esta clase.
        motion.startDeviceMotionUpdates(to: .main) { [weak self] data, _ in
            guard let self, let acceleration = data?.userAcceleration else { return }
            self.handle(acceleration: acceleration)
        }
    }

    public func stop() {
        guard isRunning else { return }
        motion.stopDeviceMotionUpdates()
        samples.removeAll()
        isRunning = false
    }

    private func handle(acceleration: CMAcceleration) {
        let now = Date()
        // CoreMotion entrega la aceleración en múltiplos de g; el umbral está en
        // m/s², así que se convierte antes de comparar.
        let magnitude = sqrt(
            acceleration.x * acceleration.x
                + acceleration.y * acceleration.y
                + acceleration.z * acceleration.z
        ) * SeismikDSP.gravity

        let previousVariance = SeismikDSP.variance(of: samples.map(\.magnitude))
        samples.append((at: now, magnitude: magnitude))
        let cutoff = now.addingTimeInterval(-SeismikDSP.window)
        samples.removeAll { $0.at < cutoff }
        if samples.count > SeismikDSP.maximumSamples {
            samples.removeFirst(samples.count - SeismikDSP.maximumSamples)
        }
        if samples.count % 80 == 0 { refreshCharging() }

        guard !isSending,
              SeismikDSP.shouldReport(
                  magnitude: magnitude,
                  previousVariance: previousVariance,
                  isCharging: isCharging,
                  secondsSinceLastPing: now.timeIntervalSince(lastPing)
              ),
              let coordinate = LocationManager.shared.userCoordinate
        else { return }

        isSending = true
        Task { [weak self] in
            guard let self else { return }
            defer { self.isSending = false }
            let delivered = await self.api.sendShake(
                latitude: coordinate.latitude,
                longitude: coordinate.longitude,
                pgaG: magnitude / SeismikDSP.gravity,
                at: now
            )
            if delivered { self.lastPing = now }
        }
    }

    private func refreshCharging() {
        let state = UIDevice.current.batteryState
        isCharging = state == .charging || state == .full
    }
}
