import 'dart:async';
import 'dart:collection';
import 'dart:math' as math;

import 'package:battery_plus/battery_plus.dart';
import 'package:sensors_plus/sensors_plus.dart';

import '../core/constants.dart';
import 'api_client.dart';
import 'motion_evidence.dart';

typedef PositionProvider =
    Future<({double latitude, double longitude})?> Function();

/// Ventana deslizante de magnitudes con varianza en tiempo constante.
///
/// El sensor entrega entre 50 y más de 200 muestras por segundo según el
/// teléfono. Recalcular la varianza recorriendo la ventana en cada muestra
/// creaba una lista nueva cada vez: trabajo y basura proporcionales a la
/// velocidad del sensor, justo en los teléfonos más rápidos.
class MotionWindow {
  MotionWindow({
    this.window = SeismikConstants.dspWindow,
    this.maximumSamples = SeismikConstants.dspMaximumSamples,
  });

  /// Con menos muestras no hay referencia para distinguir un sismo del ruido.
  static const int minimumSamples = 12;

  // Millones de sumas y restas acumulan error de redondeo; recalcular desde
  // cero cada tanto impide que el umbral se desplace con las horas.
  static const int _resyncEvery = 4096;

  final Duration window;
  final int maximumSamples;
  final ListQueue<_MagnitudeSample> _samples = ListQueue<_MagnitudeSample>();
  double _sum = 0;
  double _sumOfSquares = 0;
  int _additions = 0;

  int get length => _samples.length;

  /// Varianza poblacional de la ventana; infinita si aún no hay suficientes.
  double get variance {
    final int count = _samples.length;
    if (count < minimumSamples) return double.infinity;
    final double mean = _sum / count;
    final double value = _sumOfSquares / count - mean * mean;
    return value < 0 ? 0 : value;
  }

  void add(DateTime at, double magnitude) {
    _samples.addLast(_MagnitudeSample(at, magnitude));
    _sum += magnitude;
    _sumOfSquares += magnitude * magnitude;
    final DateTime cutoff = at.subtract(window);
    // Las muestras llegan en orden: las vencidas y las que exceden el máximo
    // están siempre al principio.
    while (_samples.isNotEmpty &&
        (_samples.first.at.isBefore(cutoff) ||
            _samples.length > maximumSamples)) {
      final _MagnitudeSample removed = _samples.removeFirst();
      _sum -= removed.magnitude;
      _sumOfSquares -= removed.magnitude * removed.magnitude;
    }
    if (++_additions % _resyncEvery == 0) _resync();
  }

  void clear() {
    _samples.clear();
    _sum = 0;
    _sumOfSquares = 0;
    _additions = 0;
  }

  void _resync() {
    double sum = 0;
    double sumOfSquares = 0;
    for (final _MagnitudeSample sample in _samples) {
      sum += sample.magnitude;
      sumOfSquares += sample.magnitude * sample.magnitude;
    }
    _sum = sum;
    _sumOfSquares = sumOfSquares;
  }
}

class AccelerometerService {
  AccelerometerService({
    required ApiClient apiClient,
    required PositionProvider positionProvider,
    Stream<UserAccelerometerEvent>? samples,
    Future<bool> Function()? chargingProvider,
    double? Function()? locationAccuracyProvider,
    bool? experimentalShadow,
  }) : _apiClient = apiClient,
       _positionProvider = positionProvider,
       _samples = samples,
       _chargingProvider = chargingProvider,
       _locationAccuracyProvider = locationAccuracyProvider,
       _experimentalShadow =
           experimentalShadow ?? SeismikConstants.crowdV2Shadow;

  /// El estado de carga cambia en minutos, no en milisegundos.
  static const Duration _batteryRefreshInterval = Duration(seconds: 60);

  final ApiClient _apiClient;
  final PositionProvider _positionProvider;
  final Stream<UserAccelerometerEvent>? _samples;
  final Future<bool> Function()? _chargingProvider;
  final double? Function()? _locationAccuracyProvider;
  final bool _experimentalShadow;
  final MotionEvidenceDetector _evidence = MotionEvidenceDetector();
  DateTime _lastPresence = DateTime.fromMillisecondsSinceEpoch(0);
  final Battery _battery = Battery();
  final MotionWindow _window = MotionWindow();
  StreamSubscription<UserAccelerometerEvent>? _subscription;
  DateTime _lastPing = DateTime.fromMillisecondsSinceEpoch(0);
  DateTime _lastBatteryCheck = DateTime.fromMillisecondsSinceEpoch(0);
  bool _sending = false;
  bool _charging = false;
  int _generation = 0;
  int samplesRead = 0;
  int reportsSent = 0;
  String? lastError;
  DateTime? lastSampleAt;
  bool get running => _subscription != null;

  Future<void> start() async {
    if (_subscription != null) return;
    final int generation = ++_generation;
    await _refreshBattery();
    if (generation != _generation) return;
    _lastBatteryCheck = DateTime.now();
    _subscription =
        (_samples ??
                userAccelerometerEventStream(
                  samplingPeriod: SensorInterval.gameInterval,
                ))
            .listen(
              _onSample,
              onError: (_) {
                lastError = 'El sistema no entrega lecturas del sensor.';
                unawaited(stop());
              },
            );
  }

  void _onSample(UserAccelerometerEvent event) {
    final DateTime now = DateTime.now();
    samplesRead++;
    lastSampleAt = now;
    final double magnitude = math.sqrt(
      event.x * event.x + event.y * event.y + event.z * event.z,
    );
    if (!magnitude.isFinite) {
      _evidence.reset();
      return;
    }
    if (_experimentalShadow) {
      final evidence = _evidence.add(
        event.timestamp,
        event.x,
        event.y,
        event.z,
      );
      if (evidence != null && !_sending) {
        _sending = true;
        unawaited(_sendShadow(evidence, _generation));
      }
      // No fall-through into the legacy candidate/push path in a v2 build.
      return;
    }
    // La varianza se calcula sobre el historial anterior al pico. Incluir el
    // propio impulso haría que un sismo real pareciera movimiento del usuario.
    final double lowFrequencyVariance = _window.variance;
    _window.add(now, magnitude);

    // Antes se consultaba cuando la ventana medía un múltiplo de 80 muestras.
    // Con un sensor rápido la ventana se llena y queda fija en 160, y la
    // consulta nativa a la batería se repetía en cada muestra.
    if (now.difference(_lastBatteryCheck) >= _batteryRefreshInterval) {
      _lastBatteryCheck = now;
      unawaited(_refreshBattery());
    }

    final bool quietDevice =
        lowFrequencyVariance <= SeismikConstants.userMotionVarianceThreshold;
    final bool aboveThreshold =
        magnitude >= SeismikConstants.shakeThresholdMetersPerSecondSquared;
    final bool cooledDown =
        now.difference(_lastPing) >= SeismikConstants.shakeCooldown;
    final bool eligibleMotion =
        quietDevice ||
        (_charging &&
            lowFrequencyVariance <=
                SeismikConstants.userMotionVarianceThreshold * 2);
    if (!aboveThreshold || !eligibleMotion || !cooledDown || _sending) {
      return;
    }

    _sending = true;
    // También enfriar intentos fallidos: no hacer una petición por muestra.
    _lastPing = now;
    unawaited(_sendPing(now, magnitude, _generation));
  }

  Future<void> _sendPing(DateTime now, double magnitude, int generation) async {
    try {
      ({double latitude, double longitude})? position;
      try {
        position = await _positionProvider();
      } catch (_) {
        lastError = 'Medición descartada: no se pudo obtener la ubicación.';
        _lastPing = DateTime.now().add(const Duration(seconds: 27));
        return;
      }
      if (generation != _generation || !running) return;
      if (position == null) {
        lastError = 'Medición descartada: no hay ubicación reciente y precisa.';
        return;
      }
      await _apiClient.sendShake(
        latitude: position.latitude,
        longitude: position.longitude,
        pgaG: magnitude / SeismikConstants.gravity,
        timestampMilliseconds: now.millisecondsSinceEpoch,
      );
      _lastPing = now;
      reportsSent++;
      lastError = null;
    } catch (_) {
      lastError =
          'No se pudo enviar la medición. Se reintentará con otra sacudida.';
      _lastPing = DateTime.now().add(const Duration(seconds: 27));
    } finally {
      _sending = false;
    }
  }

  Future<void> sendShadowPresence() async {
    if (!_experimentalShadow ||
        !_evidence.available ||
        _sending ||
        DateTime.now().difference(_lastPresence) <
            const Duration(seconds: 60)) {
      return;
    }
    if (lastSampleAt == null ||
        DateTime.now().difference(lastSampleAt!).abs() >
            const Duration(seconds: 1)) {
      return;
    }
    _lastPresence = DateTime.now();
    _sending = true;
    await _sendShadow(null, _generation);
  }

  Future<void> _sendShadow(MotionEvidence? evidence, int generation) async {
    try {
      final position = await _positionProvider();
      final accuracy = _locationAccuracyProvider?.call();
      if (generation != _generation || !running) return;
      if (position == null ||
          accuracy == null ||
          !accuracy.isFinite ||
          accuracy > 100) {
        lastError =
            'Sensor experimental: falta ubicación reciente con precisión suficiente.';
        return;
      }
      await _apiClient.sendCrowdShadow(<String, dynamic>{
        'lat': position.latitude, 'lon': position.longitude,
        'timestamp':
            (evidence?.at ?? DateTime.now()).millisecondsSinceEpoch / 1000,
        'location_accuracy_m': accuracy,
        'stationary_seconds':
            evidence?.stationarySeconds ?? _evidence.stationarySeconds,
        // Presence is not counted without a measured sampling cadence below.
        'sampling_hz': evidence?.samplingHz ?? _evidence.samplingHz,
        'max_gap_ms': evidence?.maxGapMs ?? _evidence.maxGapMs,
        if (evidence != null) ...{
          'peak_g': evidence.peakG,
          'rms_g': evidence.rmsG,
          'duration_ms': evidence.durationMs,
          'samples': evidence.samples,
          'threshold_samples': evidence.thresholdSamples,
        },
      }, presence: evidence == null);
      if (evidence != null) reportsSent++;
      lastError = null;
    } catch (_) {
      lastError =
          'Medición experimental no enviada; no se enviará como alerta.';
    } finally {
      _sending = false;
    }
  }

  Future<void> _refreshBattery() async {
    try {
      if (_chargingProvider != null) {
        _charging = await _chargingProvider();
        return;
      }
      final BatteryState state = await _battery.batteryState;
      _charging = state == BatteryState.charging || state == BatteryState.full;
    } catch (_) {
      // Sin lectura de batería se asume que no carga: el criterio más estricto.
      _charging = false;
    }
  }

  Future<void> stop() async {
    ++_generation;
    final subscription = _subscription;
    _subscription = null;
    await subscription?.cancel();
    _window.clear();
    _evidence.reset();
  }
}

class _MagnitudeSample {
  const _MagnitudeSample(this.at, this.magnitude);
  final DateTime at;
  final double magnitude;
}
