import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

/// Private to this installation and this account/circle; never sent to the API.
class FamilyNicknameStore {
  const FamilyNicknameStore();

  String _key(String uid, String circleId) =>
      'seismik.family.nicknames.${Uri.encodeComponent(uid)}.${Uri.encodeComponent(circleId)}';

  Future<Map<String, String>> load(String uid, String circleId) async {
    final prefs = await SharedPreferences.getInstance();
    try {
      final value = jsonDecode(prefs.getString(_key(uid, circleId)) ?? '{}');
      if (value is! Map) return <String, String>{};
      return <String, String>{
        for (final entry in value.entries)
          if (entry.key is String && entry.value is String)
            entry.key as String: entry.value as String,
      };
    } on FormatException {
      return <String, String>{};
    }
  }

  Future<void> save(
    String uid,
    String circleId,
    Map<String, String> names,
  ) async {
    final prefs = await SharedPreferences.getInstance();
    if (!await prefs.setString(_key(uid, circleId), jsonEncode(names))) {
      throw StateError('No se pudo guardar el sobrenombre en este celular.');
    }
  }
}
