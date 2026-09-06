import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seismik/presentation/widgets/liquid_glass.dart';

Widget host(Widget child, {Brightness brightness = Brightness.light}) =>
    CupertinoApp(
      theme: CupertinoThemeData(brightness: brightness),
      home: Center(child: child),
    );

void main() {
  testWidgets('el vidrio desenfoca lo que tiene detrás', (tester) async {
    await tester.pumpWidget(host(const LiquidGlass(child: Text('encima'))));

    final BackdropFilter filter = tester.widget(find.byType(BackdropFilter));
    expect(filter.filter, isNotNull);
    expect(find.text('encima'), findsOneWidget);
  });

  testWidgets('usa la esquina superelíptica de Apple, no un radio simple', (
    tester,
  ) async {
    await tester.pumpWidget(host(const LiquidGlass(child: Text('x'))));

    // Un ClipRRect delataría el «corner break» que no tiene iOS.
    expect(find.byType(ClipRSuperellipse), findsOneWidget);
    expect(find.byType(ClipRRect), findsNothing);
  });

  testWidgets('la variante de barra no recorta ni proyecta sombra', (
    tester,
  ) async {
    await tester.pumpWidget(host(const LiquidGlass.bar(child: Text('barra'))));

    expect(find.byType(BackdropFilter), findsOneWidget);
    expect(find.byType(ClipRSuperellipse), findsNothing);
    expect(find.text('barra'), findsOneWidget);
  });

  testWidgets('el tinte cambia entre claro y oscuro', (tester) async {
    Gradient gradientOf(WidgetTester tester) {
      final DecoratedBox box = tester.widget(
        find
            .descendant(
              of: find.byType(BackdropFilter),
              matching: find.byType(DecoratedBox),
            )
            .first,
      );
      return (box.decoration as BoxDecoration).gradient!;
    }

    await tester.pumpWidget(host(const LiquidGlass(child: Text('x'))));
    final Gradient light = gradientOf(tester);

    await tester.pumpWidget(
      host(const LiquidGlass(child: Text('x')), brightness: Brightness.dark),
    );
    final Gradient dark = gradientOf(tester);

    expect(light, isNot(equals(dark)));
  });

  testWidgets('el ajuste manual de opacidad se respeta', (tester) async {
    await tester.pumpWidget(
      host(const LiquidGlass(opacity: 0.2, child: Text('x'))),
    );

    final DecoratedBox box = tester.widget(
      find
          .descendant(
            of: find.byType(BackdropFilter),
            matching: find.byType(DecoratedBox),
          )
          .first,
    );
    final LinearGradient gradient =
        (box.decoration as BoxDecoration).gradient! as LinearGradient;
    // 0.2 + 0.16 arriba y 0.2 - 0.04 abajo para el tema claro.
    expect(gradient.colors.first.a, closeTo(0.36, 0.001));
    expect(gradient.colors.last.a, closeTo(0.16, 0.001));
  });

  testWidgets('el relleno interno se aplica al contenido', (tester) async {
    await tester.pumpWidget(
      host(
        const LiquidGlass(
          padding: EdgeInsets.all(24),
          child: Text('contenido'),
        ),
      ),
    );

    expect(
      find.descendant(
        of: find.byType(LiquidGlass),
        matching: find.byType(Padding),
      ),
      findsWidgets,
    );
    expect(find.text('contenido'), findsOneWidget);
  });

  testWidgets('la tarjeta de vidrio envuelve al material', (tester) async {
    await tester.pumpWidget(host(const LiquidGlassCard(child: Text('tarjeta'))));

    expect(find.byType(LiquidGlass), findsOneWidget);
    expect(find.text('tarjeta'), findsOneWidget);
  });

  testWidgets('se dibuja sin excepciones sobre un fondo con contenido', (
    tester,
  ) async {
    await tester.pumpWidget(
      CupertinoApp(
        home: Stack(
          children: <Widget>[
            Container(color: CupertinoColors.activeBlue),
            const Positioned(
              left: 20,
              top: 20,
              width: 200,
              height: 100,
              child: LiquidGlass(child: Text('sobre el fondo')),
            ),
          ],
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(find.text('sobre el fondo'), findsOneWidget);
  });
}
