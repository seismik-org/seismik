import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

enum ConnectionProblem { offline, service, connectionLikely, unknown, request }

class ConnectionDiagnosis {
  const ConnectionDiagnosis(this.problem, this.message, this.label);
  final ConnectionProblem problem;
  final String message;
  final String label;
}

/// Independent public check: never receives account/device credentials or data.
class ServiceStatusClient {
  ServiceStatusClient({
    required http.Client client,
    DateTime Function()? clock,
    this.timeout = const Duration(seconds: 6),
  }) : _client = client,
       _clock = clock ?? DateTime.now;

  final http.Client _client;
  final DateTime Function() _clock;
  final Duration timeout;
  Future<bool?>? _inFlight;
  DateTime? _lastAttempt;
  bool? _cached;

  Future<bool?> _apiAvailable() {
    final pending = _inFlight;
    if (pending != null) return pending;
    final age = _lastAttempt == null
        ? null
        : _clock().difference(_lastAttempt!);
    if (age != null && !age.isNegative && age < const Duration(seconds: 45)) {
      return Future.value(_cached);
    }
    return _inFlight = _check().whenComplete(() => _inFlight = null);
  }

  Future<bool?> _check() async {
    _lastAttempt = _clock();
    _cached = null;
    try {
      final response = await _client
          .get(
            Uri.parse('https://status.seismik.org/api/status'),
            headers: const {'Accept': 'application/json'},
          )
          .timeout(timeout);
      if (response.statusCode != 200 || response.bodyBytes.length > 16384) {
        return null;
      }
      final data = jsonDecode(response.body);
      if (data is! Map<String, dynamic> || data['services'] is! Map) {
        return null;
      }
      final checked = DateTime.tryParse('${data['checked_at'] ?? ''}');
      if (checked == null) return null;
      final age = _clock().difference(checked);
      if (age > const Duration(minutes: 2) ||
          age < const Duration(seconds: -30)) {
        return null;
      }
      final api = (data['services'] as Map)['api'];
      return _cached = api is bool ? api : null;
    } on Object {
      return null;
    }
  }

  Future<ConnectionDiagnosis> diagnose({
    required bool hasSignal,
    int? httpStatus,
  }) async {
    if (!hasSignal) {
      return const ConnectionDiagnosis(
        ConnectionProblem.offline,
        'El teléfono no detecta una red. Activa Wi-Fi o datos móviles. Conservamos los datos guardados y los envíos pendientes.',
        'Sin red · datos guardados',
      );
    }
    final available = await _apiAvailable();
    if (available == false) {
      return const ConnectionDiagnosis(
        ConnectionProblem.service,
        'La página de estado confirma que la API de Seismik no está disponible. Conservamos tus datos y pendientes; inténtalo más tarde.',
        'Seismik temporalmente no disponible',
      );
    }
    // A failed API request is evidence of a service/endpoint problem even if
    // the global health probe is healthy. Never blame the phone for a 5xx.
    if (httpStatus != null && httpStatus >= 500) {
      return const ConnectionDiagnosis(
        ConnectionProblem.service,
        'Seismik no pudo completar esta solicitud. Puede ser un fallo parcial del servicio. Conservamos tus datos y pendientes; vuelve a intentarlo.',
        'Problema temporal del servicio',
      );
    }
    if (available == true) {
      return const ConnectionDiagnosis(
        ConnectionProblem.connectionLikely,
        'El monitor indica que Seismik está disponible, pero este teléfono no pudo conectarse. Revisa Wi-Fi, datos móviles o VPN y vuelve a intentarlo. La causa aún no está confirmada.',
        'Conexión con Seismik interrumpida',
      );
    }
    return const ConnectionDiagnosis(
      ConnectionProblem.unknown,
      'No pudimos conectar ni comprobar la página de estado. Aún no sabemos si falla la conexión o el servicio. Conservamos tus datos y pendientes; inténtalo de nuevo.',
      'Conexión sin verificar',
    );
  }
}
