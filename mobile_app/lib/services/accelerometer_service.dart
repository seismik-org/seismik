import 'dart:async';
import 'dart:collection';
import 'dart:math' as math;

import 'package:battery_plus/battery_plus.dart';
import 'package:sensors_plus/sensors_plus.dart';

import '../core/constants.dart';
import 'api_client.dart';

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
  }) : _apiClient = apiClient,
       _positionProvider = positionProvider;

  /// El estado de carga cambia en minutos, no en milisegundos.
  static const Duration _batteryRefreshInterval = Duration(seconds: 60);

  final ApiClient _apiClient;
  final PositionProvider _positionProvider;
  final Battery _battery = Battery();
  final MotionWindow _window = MotionWindow();
  StreamSubscription<UserAccelerometerEvent>? _subscription;
  DateTime _lastPing = DateTime.fromMillisecondsSinceEpoch(0);
  DateTime _lastBatteryCheck = DateTime.fromMillisecondsSinceEpoch(0);
  bool _sending = false;
  bool _charging = false;

  Future<void> start() async {
    if (_subscription != null) return;
    await _refreshBattery();
    _lastBatteryCheck = DateTime.now();
    _subscription =
        userAccelerometerEventStream(
          samplingPeriod: SensorInterval.gameInterval,
        ).listen(
          _onSample,
          onError: (_) {
            unawaited(stop());
          },
        );
  }

  void _onSample(UserAccelerometerEvent event) {
    final DateTime now = DateTime.now();
    final double magnitude = math.sqrt(
      event.x * event.x + event.y * event.y + event.z * event.z,
    );
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
    unawaited(_sendPing(now, magnitude));
  }

  Future<void> _sendPing(DateTime now, double magnitude) async {
    try {
      final ({double latitude, double longitude})? position =
          await _positionProvider();
      if (position == null) return;
      await _apiClient.sendShake(
        latitude: position.latitude,
        longitude: position.longitude,
        pgaG: magnitude / SeismikConstants.gravity,
        timestampMilliseconds: now.millisecondsSinceEpoch,
      );
      _lastPing = now;
    } catch (_) {
      // Un pico no enviado no debe tumbar el flujo del sensor; el siguiente
      // pico válido lo reintenta.
    } finally {
      _sending = false;
    }
  }

  Future<void> _refreshBattery() async {
    try {
      final BatteryState state = await _battery.batteryState;
      _charging = state == BatteryState.charging || state == BatteryState.full;
    } catch (_) {
      // Sin lectura de batería se asume que no carga: el criterio más estricto.
      _charging = false;
    }
  }

  Future<void> stop() async {
    await _subscription?.cancel();
    _subscription = null;
    _window.clear();
  }
}

class _MagnitudeSample {
  const _MagnitudeSample(this.at, this.magnitude);
  final DateTime at;
  final double magnitude;
}
