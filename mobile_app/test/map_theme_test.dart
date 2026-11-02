import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';
import 'package:seismik/core/map_theme.dart';
import 'package:seismik/presentation/widgets/bottom_navigation.dart';

void main() {
  test('dark map style is valid JSON and keeps geographic labels', () {
    final rules = jsonDecode(SeismikMapTheme.darkStyle) as List<dynamic>;
    expect(rules, isNotEmpty);
    expect(rules.any((dynamic rule) => rule['featureType'] == 'water'), isTrue);
    expect(SeismikMapTheme.darkStyle, isNot(contains('"visibility":"off"')));
  });

  testWidgets(
    'map follows system brightness and restores the default light map',
    (tester) async {
      addTearDown(tester.platformDispatcher.clearPlatformBrightnessTestValue);
      tester.platformDispatcher.platformBrightnessTestValue = Brightness.light;
      String? style;
      MapColorScheme? scheme;
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.light(),
          darkTheme: ThemeData.dark(),
          home: Builder(
            builder: (context) {
              style = SeismikMapTheme.style(context);
              scheme = SeismikMapTheme.colorScheme(context);
              return const SizedBox();
            },
          ),
        ),
      );
      expect(style, isNull);
      expect(scheme, MapColorScheme.light);
      tester.platformDispatcher.platformBrightnessTestValue = Brightness.dark;
      await tester.pumpAndSettle();
      expect(style, SeismikMapTheme.darkStyle);
      expect(scheme, MapColorScheme.dark);
      tester.platformDispatcher.platformBrightnessTestValue = Brightness.light;
      await tester.pumpAndSettle();
      expect(style, isNull);
      expect(scheme, MapColorScheme.light);
    },
  );

  for (final scale in <double>[1, 1.5, 2]) {
    testWidgets(
      'navigation keeps labels on one line at 320px and scale $scale',
      (tester) async {
        tester.view.physicalSize = const Size(320, 640);
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);
        var selected = 0;
        await tester.pumpWidget(
          MaterialApp(
            home: MediaQuery(
              data: MediaQueryData(textScaler: TextScaler.linear(scale)),
              child: Scaffold(
                bottomNavigationBar: SeismikBottomNavigation(
                  selectedIndex: 0,
                  onSelected: (value) => selected = value,
                ),
              ),
            ),
          ),
        );
        expect(tester.takeException(), isNull);
        final label = find.text('Ajustes');
        final context = tester.element(label);
        expect(DefaultTextStyle.of(context).maxLines, 1);
        expect(DefaultTextStyle.of(context).softWrap, isFalse);
        expect(find.byTooltip('Configuración'), findsWidgets);
        await tester.tap(label);
        expect(selected, 4);
        expect(tester.takeException(), isNull);
      },
    );
  }
}
