import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Recuerda las alarmas que ya sonaron para que un mismo sismo no suene dos veces.
///
/// Un sismo llega como varios avisos críticos: la detección preliminar, la
/// alerta del catálogo oficial y el reporte de sacudida fuerte, separados por
/// minutos y con identificadores distintos. Sonar con cada uno era lo que hacía
/// que la app siguiera pitando después de «Cerrar». Los avisos siguientes del
/// mismo sismo llegan como notificación normal; una réplica posterior, con otra
/// hora de origen, vuelve a sonar.
///
/// Vive en SharedPreferences porque el aviso puede llegar con la app cerrada,
/// en el isolate de fondo de Firebase, y la decisión tiene que ser la misma.
class AlertMemory {
  AlertMemory({Future<SharedPreferences> Function()? preferences})
    : _preferences = preferences ?? SharedPreferences.getInstance;

  static const String _key = 'alerts.rung';

  /// Diferencia máxima entre horas de origen para tratarlos como un solo sismo.
  static const Duration sameQuakeWindow = Duration(minutes: 3);

  /// Distancia máxima entre epicentros, con margen para la ubicación estimada
  /// de una detección preliminar.
  static const double sameQuakeDistanceKm = 300;

  /// Un reporte oficial deja de llegar como alarma a los 30 minutos; una hora
  /// cubre todos los avisos del mismo sismo.
  static const Duration keepFor = Duration(hours: 1);

  final Future<SharedPreferences> Function() _preferences;

  /// Si ya sonó una alarma por este mismo sismo.
  Future<bool> alreadyRang(Map<String, dynamic> data, {DateTime? now}) async {
    final RungAlert? alert = RungAlert.fromData(data);
    if (alert == null) return false;
    final List<RungAlert> rung = await _load(now ?? DateTime.now().toUtc());
    return rung.any((RungAlert known) => known.isSameQuake(alert));
  }

  /// Anota una alarma que acaba de sonar. Las pruebas locales y los simulacros
  /// no se anotan: no pueden silenciar un sismo real que llegue justo después.
  Future<void> remember(Map<String, dynamic> data, {DateTime? now}) async {
    final RungAlert? alert = RungAlert.fromData(data, savedAt: now);
    if (alert == null || alert.isRehearsal) return;
    final DateTime moment = now ?? DateTime.now().toUtc();
    final List<RungAlert> rung = await _load(moment);
    final SharedPreferences preferences = await _preferences();
    await preferences.setString(
      _key,
      jsonEncode(<Map<String, Object?>>[
        for (final RungAlert known in rung) known.toJson(),
        alert.toJson(),
      ]),
    );
  }

  Future<List<RungAlert>> _load(DateTime now) async {
    final SharedPreferences preferences = await _preferences();
    // El otro isolate pudo escribir mientras éste tenía la caché abierta.
    await preferences.reload();
    final String? raw = preferences.getString(_key);
    if (raw == null) return <RungAlert>[];
    try {
      final Object? decoded = jsonDecode(raw);
      if (decoded is! List) return <RungAlert>[];
      return <RungAlert>[
        for (final Object? item in decoded)
          if (item is Map<String, dynamic>)
            if (RungAlert.fromJson(item) case final RungAlert alert
                when now.difference(alert.savedAt) < keepFor)
              alert,
      ];
    } on FormatException {
      return <RungAlert>[];
    }
  }
}

@immutable
class RungAlert {
  const RungAlert({
    required this.id,
    required this.at,
    required this.savedAt,
    this.latitude,
    this.longitude,
  });

  /// `null` si el aviso no trae ni identificador ni hora: sin esos datos no hay
  /// forma de saber si es el mismo sismo, así que suena.
  static RungAlert? fromData(Map<String, dynamic> data, {DateTime? savedAt}) {
    final String id = (data['event_id'] ?? '').toString();
    final DateTime? at = DateTime.tryParse(
      (data['detected_at'] ?? data['origin_time'] ?? '').toString(),
    )?.toUtc();
    if (id.isEmpty || at == null) return null;
    return RungAlert(
      id: id,
      at: at,
      savedAt: savedAt ?? DateTime.now().toUtc(),
      latitude: _number(data['latitude'] ?? data['estimated_latitude']),
      longitude: _number(data['longitude'] ?? data['estimated_longitude']),
    );
  }

  static RungAlert? fromJson(Map<String, dynamic> json) {
    final DateTime? at = DateTime.tryParse('${json['at']}');
    final DateTime? savedAt = DateTime.tryParse('${json['saved_at']}');
    final String id = '${json['id'] ?? ''}';
    if (id.isEmpty || at == null || savedAt == null) return null;
    return RungAlert(
      id: id,
      at: at,
      savedAt: savedAt,
      latitude: _number(json['latitude']),
      longitude: _number(json['longitude']),
    );
  }

  final String id;
  final DateTime at;
  final DateTime savedAt;
  final double? latitude;
  final double? longitude;

  bool get isRehearsal =>
      id.startsWith('local-critical-test-') || id.startsWith('drill-');

  Map<String, Object?> toJson() => <String, Object?>{
    'id': id,
    'at': at.toIso8601String(),
    'saved_at': savedAt.toIso8601String(),
    'latitude': latitude,
    'longitude': longitude,
  };

  bool isSameQuake(RungAlert other) {
    if (id == other.id) return true;
    if (at.difference(other.at).abs() > AlertMemory.sameQuakeWindow) {
      return false;
    }
    final double? lat = latitude, lon = longitude;
    final double? otherLat = other.latitude, otherLon = other.longitude;
    // Una detección sin ubicar, a la misma hora, es el mismo movimiento.
    if (lat == null || lon == null || otherLat == null || otherLon == null) {
      return true;
    }
    return _distanceKm(lat, lon, otherLat, otherLon) <=
        AlertMemory.sameQuakeDistanceKm;
  }

  static double? _number(Object? value) => switch (value) {
    final num number => number.toDouble(),
    final String text => double.tryParse(text),
    _ => null,
  };

  static double _distanceKm(
    double lat1,
    double lon1,
    double lat2,
    double lon2,
  ) {
    const double radians = math.pi / 180;
    final double halfLat = math.sin((lat2 - lat1) * radians / 2);
    final double halfLon = math.sin((lon2 - lon1) * radians / 2);
    final double inner =
        halfLat * halfLat +
        math.cos(lat1 * radians) * math.cos(lat2 * radians) * halfLon * halfLon;
    return 2 * 6371.0088 * math.asin(math.min(1.0, math.sqrt(inner)));
  }
}
