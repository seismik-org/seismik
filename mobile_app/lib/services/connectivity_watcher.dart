import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';

/// Cuándo está activo el modo de emergencia: solo, sin señal; apagado, con señal.
/// La persona puede dejarlo fijo (por ejemplo con una señal tan débil que nada
/// carga) y entonces sólo ella lo apaga.
bool emergencyModeWanted({required bool hasSignal, required bool pinned}) =>
    !hasSignal || pinned;

/// ¿Alguna de las redes que ve el sistema da salida?
bool hasSignalIn(List<ConnectivityResult> results) => results.any(
  (ConnectivityResult result) => result != ConnectivityResult.none,
);

/// Avisa cuando el teléfono pierde o recupera la red.
///
/// Un corte de unos segundos (un túnel, un cambio de antena) no activa el modo,
/// y una red que acaba de volver espera un instante a estabilizarse antes de
/// apagarlo. Sin el plugin (pruebas) se considera que hay señal.
class ConnectivityWatcher {
  ConnectivityWatcher({
    Stream<List<ConnectivityResult>>? changes,
    Future<List<ConnectivityResult>> Function()? current,
    this.lostAfter = const Duration(seconds: 4),
    this.backAfter = const Duration(milliseconds: 1500),
  }) : _changes = changes,
       _current = current;

  final Stream<List<ConnectivityResult>>? _changes;
  final Future<List<ConnectivityResult>> Function()? _current;
  final Duration lostAfter;
  final Duration backAfter;
  StreamSubscription<List<ConnectivityResult>>? _subscription;
  Timer? _timer;
  bool? _last;

  Future<void> start(void Function(bool hasSignal) onChange) async {
    void consider(bool reachable) {
      _timer?.cancel();
      _timer = Timer(reachable ? backAfter : lostAfter, () {
        if (_last == reachable) return;
        _last = reachable;
        onChange(reachable);
      });
    }

    try {
      _subscription = (_changes ?? Connectivity().onConnectivityChanged).listen(
        (List<ConnectivityResult> results) => consider(hasSignalIn(results)),
        onError: (Object _) {},
      );
      consider(
        hasSignalIn(await (_current ?? Connectivity().checkConnectivity)()),
      );
    } catch (_) {
      // Sin plugin (pruebas) no hay nada que vigilar: se asume señal.
    }
  }

  Future<void> dispose() async {
    _timer?.cancel();
    await _subscription?.cancel();
  }
}
