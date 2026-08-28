import 'package:shared_preferences/shared_preferences.dart';

class AgencyPreferenceStore {
  const AgencyPreferenceStore();

  static const String _prefix = 'seismik.report-agencies.';

  Future<Set<String>> load(String eventKey) async {
    final SharedPreferences preferences = await SharedPreferences.getInstance();
    return (preferences.getStringList('$_prefix$eventKey') ?? <String>[])
        .toSet();
  }

  Future<void> save(String eventKey, Set<String> agencyIds) async {
    final SharedPreferences preferences = await SharedPreferences.getInstance();
    final List<String> ordered = agencyIds.toList()..sort();
    await preferences.setStringList('$_prefix$eventKey', ordered);
  }
}
