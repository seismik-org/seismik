import AVFoundation
import AudioToolbox
import Foundation

/// Reproductor de alarma sismica de emergencia con capacidad de sonar en modo silencio.
public final class AlertSoundPlayer: NSObject, ObservableObject, AVAudioPlayerDelegate {
    public static let shared = AlertSoundPlayer()

    @Published public private(set) var isPlaying: Bool = false

    private var audioPlayer: AVAudioPlayer?
    private var sirenTimer: Timer?

    private override init() {
        super.init()
    }

    /// Inicia la alarma sismica continua de emergencia.
    public func playSiren() {
        guard !isPlaying else { return }
        isPlaying = true

        configureAudioSession()

        // 1. Vibracion y alerta del sistema inmediata
        AudioServicesPlayAlertSound(SystemSoundID(kSystemSoundID_Vibrate))
        AudioServicesPlaySystemSound(1005)

        // 2. Reproduccion de la sirena sismica continua modulada
        if let wavData = generateSeismicSirenWAV() {
            do {
                audioPlayer = try AVAudioPlayer(data: wavData)
                audioPlayer?.delegate = self
                audioPlayer?.numberOfLoops = -1 // Bucle infinito hasta descarte
                audioPlayer?.volume = 1.0
                audioPlayer?.prepareToPlay()
                audioPlayer?.play()
            } catch {
                // Respaldo por AudioServices
                startAudioServicesFallback()
            }
        } else {
            startAudioServicesFallback()
        }
    }

    /// Detiene la alarma sismica de emergencia.
    public func stop() {
        isPlaying = false
        audioPlayer?.stop()
        audioPlayer = nil
        sirenTimer?.invalidate()
        sirenTimer = nil

        do {
            try AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        } catch {}
    }

    private func configureAudioSession() {
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playback, mode: .voicePrompt, options: [.duckOthers])
            try session.setActive(true)
        } catch {
            // Intentar con configuracion basica de reproduccion
            try? AVAudioSession.sharedInstance().setCategory(.playback)
            try? AVAudioSession.sharedInstance().setActive(true)
        }
    }

    private func startAudioServicesFallback() {
        sirenTimer?.invalidate()
        sirenTimer = Timer.scheduledTimer(withTimeInterval: 1.2, repeats: true) { [weak self] _ in
            guard let self = self, self.isPlaying else { return }
            AudioServicesPlaySystemSound(1005)
            AudioServicesPlayAlertSound(SystemSoundID(kSystemSoundID_Vibrate))
        }
    }

    /// Genera en memoria un buffer WAV PCM de 2 segundos con una sirena sismica modulada en frecuencia (650Hz - 1150Hz).
    private func generateSeismicSirenWAV() -> Data? {
        let sampleRate = 22050
        let durationSeconds = 2.0
        let numSamples = Int(Double(sampleRate) * durationSeconds)
        let numChannels = 1
        let bitsPerSample = 16
        let byteRate = sampleRate * numChannels * (bitsPerSample / 8)
        let blockAlign = numChannels * (bitsPerSample / 8)
        let subchunk2Size = numSamples * (bitsPerSample / 8)
        let chunkSize = 36 + subchunk2Size

        var data = Data()
        data.reserveCapacity(44 + subchunk2Size)

        // Encabezado RIFF
        data.append(contentsOf: "RIFF".utf8)
        data.append(contentsOf: withUnsafeBytes(of: UInt32(chunkSize).littleEndian) { Array($0) })
        data.append(contentsOf: "WAVE".utf8)

        // Subfragmento fmt
        data.append(contentsOf: "fmt ".utf8)
        data.append(contentsOf: withUnsafeBytes(of: UInt32(16).littleEndian) { Array($0) })
        data.append(contentsOf: withUnsafeBytes(of: UInt16(1).littleEndian) { Array($0) }) // PCM
        data.append(contentsOf: withUnsafeBytes(of: UInt16(numChannels).littleEndian) { Array($0) })
        data.append(contentsOf: withUnsafeBytes(of: UInt32(sampleRate).littleEndian) { Array($0) })
        data.append(contentsOf: withUnsafeBytes(of: UInt32(byteRate).littleEndian) { Array($0) })
        data.append(contentsOf: withUnsafeBytes(of: UInt16(blockAlign).littleEndian) { Array($0) })
        data.append(contentsOf: withUnsafeBytes(of: UInt16(bitsPerSample).littleEndian) { Array($0) })

        // Subfragmento data
        data.append(contentsOf: "data".utf8)
        data.append(contentsOf: withUnsafeBytes(of: UInt32(subchunk2Size).littleEndian) { Array($0) })

        // Generacion de onda senoidal con modulacion de frecuencia (alerta sismica)
        var phase: Double = 0.0
        let twoPi = 2.0 * Double.pi
        let maxAmp: Double = 28000.0 // Cerca del maximo de 16-bit sin saturacion

        for i in 0..<numSamples {
            let t = Double(i) / Double(sampleRate)
            // Modulacion senoidal de la frecuencia entre 650Hz y 1150Hz cada 0.66 segundos
            let currentFreq = 900.0 + 250.0 * sin(twoPi * 1.5 * t)
            phase += twoPi * currentFreq / Double(sampleRate)
            if phase > twoPi { phase -= twoPi }

            let sample = Int16(sin(phase) * maxAmp)
            data.append(contentsOf: withUnsafeBytes(of: sample.littleEndian) { Array($0) })
        }

        return data
    }
}
