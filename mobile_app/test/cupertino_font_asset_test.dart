import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test('Cupertino icons include their font, not missing-glyph boxes', () async {
    final data = await rootBundle.load(
      'packages/cupertino_icons/assets/CupertinoIcons.ttf',
    );
    expect(data.lengthInBytes, greaterThan(1000));
  });
}
