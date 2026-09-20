import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;

import 'api.dart';

/// Un integrante del círculo, con lo último que avisó.
class FamilyMember {
  const FamilyMember({
    required this.name,
    required this.isYou,
    this.needsHelp,
    this.reportedAt,
  });

  factory FamilyMember.fromMap(Map<String, dynamic> map) {
    final Object? status = map['status'];
    final Map<String, dynamic>? report = status is Map<String, dynamic>
        ? status
        : null;
    return FamilyMember(
      name: '${map['display_name'] ?? 'Familiar'}',
      isYou: map['is_you'] == true,
      needsHelp: report == null ? null : report['status'] == 'need_help',
      reportedAt: report == null
          ? null
          : DateTime.tryParse(
              '${report['reported_at'] ?? ''}'.replaceAll(
                RegExp(r'\.\d+'),
                '',
              ),
            )?.toUtc(),
    );
  }

  final String name;
  final bool isYou;

  /// `null` cuando esa persona todavía no ha avisado nada.
  final bool? needsHelp;
  final DateTime? reportedAt;

  String get statusLabel => switch (needsHelp) {
    true => 'Necesita ayuda',
    false => 'Está bien',
    null => 'Sin aviso',
  };
}

/// El círculo familiar visto desde el reloj.
class FamilyCircle {
  const FamilyCircle({required this.name, required this.members});

  factory FamilyCircle.fromMap(Map<String, dynamic> map) => FamilyCircle(
    name: '${map['circle_name'] ?? 'Mi familia'}',
    members: <FamilyMember>[
      for (final Object? item
          in (map['members'] as List<Object?>? ?? const <Object?>[]))
        if (item is Map<String, dynamic>) FamilyMember.fromMap(item),
    ],
  );

  final String name;
  final List<FamilyMember> members;
}

/// Familia en el reloj.
///
/// La sesión de la cuenta la publica el teléfono por el Data Layer: aquí no se
/// inicia sesión ni se guarda nada. Sin teléfono emparejado o con la sesión
/// cerrada, la pantalla lo dice en lugar de fallar.
class WearFamily {
  WearFamily({
    http.Client? client,
    MethodChannel channel = const MethodChannel('seismik/wear'),
    String? baseUrl,
  }) : _client = client ?? http.Client(),
       _channel = channel,
       baseUrl = baseUrl ?? SeismikWearApi.defaultBaseUrl;

  final http.Client _client;
  final MethodChannel _channel;
  final String baseUrl;

  String? _session;

  /// La sesión que comparte el teléfono, o `null` si no hay ninguna.
  Future<String?> session() async {
    try {
      final Map<Object?, Object?>? shared = await _channel
          .invokeMapMethod<Object?, Object?>('accountSession');
      final Object? token = shared?['session'];
      _session = token is String && token.isNotEmpty ? token : null;
    } on PlatformException {
      _session = null;
    } on MissingPluginException {
      _session = null;
    }
    return _session;
  }

  Future<Map<String, String>> _headers(String token) async =>
      <String, String>{'X-Seismik-Account-Session': token};

  /// El círculo con el estado de cada quien.
  Future<FamilyCircle?> circle() async {
    final String? token = _session ?? await session();
    if (token == null) return null;
    final http.Response response = await _client
        .get(
          Uri.parse('$baseUrl/v1/family/circle'),
          headers: await _headers(token),
        )
        .timeout(const Duration(seconds: 20));
    if (response.statusCode == 404) return null;
    if (response.statusCode == 401) {
      _session = null;
      throw const SeismikWearException(
        'La sesión del teléfono caducó. Ábrela allí y vuelve a intentarlo.',
      );
    }
    if (response.statusCode >= 400) {
      throw SeismikWearException(
        'No se pudo consultar a tu familia (${response.statusCode}).',
      );
    }
    return FamilyCircle.fromMap(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  /// «Estoy bien» o «Necesito ayuda». El reloj no comparte ubicación: la
  /// comparte el teléfono, que es quien la tiene con permiso de la persona.
  Future<void> report({required bool needsHelp, String? eventId}) async {
    final String? token = _session ?? await session();
    if (token == null) {
      throw const SeismikWearException(
        'Inicia sesión en el teléfono para avisar a tu familia.',
      );
    }
    final http.Response response = await _client
        .put(
          Uri.parse('$baseUrl/v1/family/status'),
          headers: <String, String>{
            ...await _headers(token),
            'Content-Type': 'application/json',
          },
          body: jsonEncode(<String, dynamic>{
            'status': needsHelp ? 'need_help' : 'safe',
            'event_id': ?eventId,
          }),
        )
        .timeout(const Duration(seconds: 20));
    if (response.statusCode == 401) {
      _session = null;
      throw const SeismikWearException(
        'La sesión del teléfono caducó. Ábrela allí y vuelve a intentarlo.',
      );
    }
    if (response.statusCode == 404) {
      throw const SeismikWearException(
        'Todavía no perteneces a un círculo familiar. Créalo en el teléfono.',
      );
    }
    if (response.statusCode >= 400) {
      throw SeismikWearException(
        'No se pudo enviar tu aviso (${response.statusCode}).',
      );
    }
  }
}
