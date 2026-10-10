import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:seismik/services/family_nickname_store.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const store = FamilyNicknameStore();
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));
  test('persists locally, isolated by account and circle', () async {
    await store.save('ana', 'casa', <String, String>{'luis': 'Papá'});
    expect(await store.load('ana', 'casa'), <String, String>{'luis': 'Papá'});
    expect(await store.load('luis', 'casa'), isEmpty);
    expect(await store.load('ana', 'otra'), isEmpty);
    await store.save('ana', 'casa', <String, String>{});
    expect(await store.load('ana', 'casa'), isEmpty);
  });
  test('corrupt preference does not block family loading', () async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('seismik.family.nicknames.a.c', '{invalid');
    expect(await store.load('a', 'c'), isEmpty);
  });
}
