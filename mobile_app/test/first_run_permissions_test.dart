import 'package:flutter_test/flutter_test.dart';
import 'package:seismik/services/first_run_permissions.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  test('asks once on the very first launch and never again', () async {
    int asked = 0;
    Future<bool> request() async {
      asked++;
      return false;
    }

    expect(await const FirstRunPermissions().runOnce(request), isTrue);
    expect(await const FirstRunPermissions().runOnce(request), isFalse);
    expect(await const FirstRunPermissions().runOnce(request), isFalse);
    expect(asked, 1);
  });

  test('is marked done before the settings page takes the person away', () async {
    final SharedPreferences preferences = await SharedPreferences.getInstance();
    bool markedWhileAsking = false;

    await const FirstRunPermissions().runOnce(() async {
      markedWhileAsking =
          preferences.getBool(FirstRunPermissions.criticalAccessKey) ?? false;
      return true;
    });

    expect(markedWhileAsking, isTrue);
  });

  test('a person who already went through it is not asked again', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{
      FirstRunPermissions.criticalAccessKey: true,
    });

    expect(await const FirstRunPermissions().runOnce(() async => true), isFalse);
  });
}
