import 'package:shared_preferences/shared_preferences.dart';

/// Only device-local preferences; never sent to the API or family automatically.
class EmergencyStore {
  static const String modeKey = 'seismik.emergency.offline_mode';
  static const String notesKey = 'seismik.emergency.meeting_notes';
  static const String cacheDateKey = 'seismik.events_cached_at';

  static Future<bool> enabled() async =>
      (await SharedPreferences.getInstance()).getBool(modeKey) ?? false;
  static Future<void> setEnabled(bool value) async =>
      (await SharedPreferences.getInstance()).setBool(modeKey, value);
  static Future<String> notes() async =>
      (await SharedPreferences.getInstance()).getString(notesKey) ?? '';
  static Future<void> saveNotes(String value) async =>
      (await SharedPreferences.getInstance()).setString(notesKey, value);
  static Future<DateTime?> cachedAt() async {
    final int? value = (await SharedPreferences.getInstance()).getInt(
      cacheDateKey,
    );
    return value == null ? null : DateTime.fromMillisecondsSinceEpoch(value);
  }
}
