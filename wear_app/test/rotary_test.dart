import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seismik_wear/rotary.dart';

/// La corona es la forma natural de recorrer una pantalla de reloj. Estas
/// pruebas fijan que mueve la lista, que no se sale por los extremos y que no
/// arrastra la pantalla de debajo cuando hay otra encima.
void main() {
  late StreamController<dynamic> crown;
  late ScrollController scroll;

  setUp(() {
    crown = StreamController<dynamic>.broadcast();
    scroll = ScrollController();
  });

  tearDown(() async {
    scroll.dispose();
    await crown.close();
  });

  Widget list({required ScrollController controller, required Key key}) =>
      RotaryScroll(
        controller: controller,
        events: crown.stream,
        child: ListView(
          key: key,
          controller: controller,
          children: <Widget>[
            for (int i = 0; i < 40; i++)
              SizedBox(height: 40, child: Text('$i')),
          ],
        ),
      );

  testWidgets('girar la corona mueve la lista', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(426, 426);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(
      MaterialApp(
        home: list(controller: scroll, key: const Key('inicio')),
      ),
    );

    crown.add(120.0);
    await tester.pump();

    expect(scroll.position.pixels, 120);
  });

  testWidgets('no se pasa de los extremos', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(426, 426);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(
      MaterialApp(
        home: list(controller: scroll, key: const Key('inicio')),
      ),
    );

    crown.add(-500.0);
    await tester.pump();
    expect(scroll.position.pixels, 0, reason: 'arriba del todo no hay más');

    crown.add(99999.0);
    await tester.pump();
    expect(scroll.position.pixels, scroll.position.maxScrollExtent);
  });

  testWidgets('con Familia encima, la lista de atrás se queda quieta', (
    WidgetTester tester,
  ) async {
    tester.view.physicalSize = const Size(426, 426);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    final ScrollController encima = ScrollController();
    addTearDown(encima.dispose);
    final GlobalKey<NavigatorState> navigator = GlobalKey<NavigatorState>();

    await tester.pumpWidget(
      MaterialApp(
        navigatorKey: navigator,
        home: list(controller: scroll, key: const Key('inicio')),
      ),
    );

    unawaited(
      navigator.currentState!.push(
        MaterialPageRoute<void>(
          builder: (_) => list(controller: encima, key: const Key('familia')),
        ),
      ),
    );
    await tester.pumpAndSettle();

    crown.add(80.0);
    await tester.pump();

    expect(encima.position.pixels, 80, reason: 'la de encima sí se mueve');
    expect(scroll.position.pixels, 0, reason: 'la de atrás no');
  });
}
