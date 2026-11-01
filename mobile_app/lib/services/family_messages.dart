import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:uuid/uuid.dart';

import 'api_client.dart';
import '../data/models/family_circle.dart';

/// Only membership/names are cached: never revive an expired location/check-in.
class FamilyCircleCache {
  static const _storage = FlutterSecureStorage();
  static String _key(String uid) =>
      'family.circle.${sha256.convert(utf8.encode(uid))}';
  static Future<void> save(String uid, FamilyCircle circle) => _storage.write(
    key: _key(uid),
    value: jsonEncode({
      'circle_id': circle.circleId,
      'circle_name': circle.circleName,
      'is_owner': circle.isOwner,
      'automatic_location_sharing': circle.automaticLocationSharing,
      'members': circle.members
          .map(
            (m) => {
              'member_id': m.memberId,
              'display_name': m.displayName,
              'is_you': m.isYou,
              'is_owner': m.isOwner,
            },
          )
          .toList(),
    }),
  );
  static Future<FamilyCircle?> load(String uid) async {
    final raw = await _storage.read(key: _key(uid));
    return raw == null
        ? null
        : FamilyCircle.fromMap(jsonDecode(raw) as Map<String, dynamic>);
  }

  static Future<void> clear(String uid) => _storage.delete(key: _key(uid));
}

/// Account/circle-scoped, device-encrypted outbox. Never sends to a new circle.
class FamilyMessages {
  FamilyMessages({
    required this.api,
    required String uid,
    required this.circleId,
    required this.senderId,
    FlutterSecureStorage? storage,
  }) : _storage = storage ?? const FlutterSecureStorage(),
       _key =
           'family.messages.${sha256.convert(utf8.encode('$uid:$circleId'))}';

  final ApiClient api;
  final String circleId;
  final String senderId;
  final FlutterSecureStorage _storage;
  final String _key;
  bool _syncing = false;
  List<Map<String, dynamic>> pending = [];
  List<Map<String, dynamic>> received = [];
  String? notice;

  Future<void> load() async {
    final raw = await _storage.read(key: _key);
    if (raw == null) return;
    try {
      final data = jsonDecode(raw) as Map<String, dynamic>;
      pending = (data['pending'] as List).cast<Map<String, dynamic>>();
      received = (data['received'] as List).cast<Map<String, dynamic>>();
      received.removeWhere(
        (m) =>
            !(DateTime.tryParse(
                  m['expires_at']?.toString() ?? '',
                )?.isAfter(DateTime.now()) ??
                false),
      );
    } on Object {
      notice = 'No se pudo leer la copia guardada de los mensajes.';
    }
  }

  Future<void> enqueue(String text, {DateTime? now}) async {
    final value = text.trim();
    if (value.isEmpty || value.runes.length > 280) {
      throw ArgumentError('Escribe entre 1 y 280 caracteres.');
    }
    if (pending.length >= 50) {
      throw StateError(
        'Tienes 50 mensajes pendientes. Revisa o cancela alguno.',
      );
    }
    pending.add({
      'message_id': const Uuid().v4(),
      'circle_id': circleId,
      'sender_id': senderId,
      'text': value,
      'created_at': (now ?? DateTime.now()).toUtc().toIso8601String(),
    });
    await _save();
  }

  Future<void> cancel(String id) async {
    pending.removeWhere((m) => m['message_id'] == id);
    await _save();
  }

  Future<void> sync({DateTime? now}) async {
    if (_syncing) return;
    _syncing = true;
    notice = null;
    try {
      final moment = now ?? DateTime.now();
      // UI disables editing while syncing. IDs survive every network retry.
      for (final message in List<Map<String, dynamic>>.of(pending)) {
        if (moment.difference(DateTime.parse(message['created_at'] as String)) >
            const Duration(hours: 24)) {
          notice =
              'Hay mensajes de más de 24 horas. Revísalos antes de volver a enviarlos.';
          continue;
        }
        try {
          await api.sendFamilyMessage(message);
          pending.removeWhere((m) => m['message_id'] == message['message_id']);
          await _save();
        } on SeismikApiException catch (error) {
          notice = error.statusCode == 429
              ? 'Se alcanzó un límite de mensajes. Sigue guardado: espera o usa SMS.'
              : error.isPermanent
              ? 'El servidor no aceptó un mensaje. Sigue guardado para que lo revises.'
              : 'Pendiente de conexión. Reintentaremos al abrir Familia.';
          break;
        } on Object {
          notice = 'Pendiente de conexión. Reintentaremos al abrir Familia.';
          break;
        }
      }
      try {
        final result = await api.fetchFamilyMessages(senderId);
        if (result['circle_id'] != circleId) {
          notice =
              'Tu círculo cambió. Los pendientes no se enviarán a otra familia.';
          return;
        }
        received = (result['messages'] as List).cast<Map<String, dynamic>>();
        await _save();
      } on Object {
        notice ??= 'Mostrando la última copia guardada. No se pudo actualizar.';
      }
    } finally {
      _syncing = false;
    }
  }

  Future<void> _save() => _storage.write(
    key: _key,
    value: jsonEncode({'pending': pending, 'received': received}),
  );
}
