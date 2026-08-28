import 'package:flutter_test/flutter_test.dart';
import 'package:seismik/services/agency_preference_store.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test(
    'agency selection is persisted independently for each earthquake',
    () async {
      SharedPreferences.setMockInitialValues(<String, Object>{});
      const AgencyPreferenceStore store = AgencyPreferenceStore();

      await store.save('quake-a', <String>{'usgs_dyfi', 'sgc'});
      await store.save('quake-b', <String>{'sgc'});

      expect(await store.load('quake-a'), <String>{'sgc', 'usgs_dyfi'});
      expect(await store.load('quake-b'), <String>{'sgc'});
    },
  );
}
