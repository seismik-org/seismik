import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seismik/presentation/widgets/bottom_navigation.dart';

void main() {
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
