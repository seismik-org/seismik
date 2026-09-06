import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seismik/presentation/widgets/adaptive.dart';
import 'package:seismik/presentation/widgets/liquid_glass.dart';

/// El framework verifica, al terminar cada prueba, que la plataforma simulada
/// quedó restaurada. Por eso la restauración va dentro del cuerpo y no en un
/// `tearDown`, que se ejecuta demasiado tarde.
Future<void> withPlatform(
  TargetPlatform platform,
  Future<void> Function() body,
) async {
  debugDefaultTargetPlatformOverride = platform;
  try {
    await body();
  } finally {
    debugDefaultTargetPlatformOverride = null;
  }
}

Widget host(Widget child) => MaterialApp(home: child);

void main() {
  group('AdaptiveScreen', () {
    testWidgets('en iPhone usa el andamiaje de Cupertino', (tester) async {
      await withPlatform(TargetPlatform.iOS, () async {
        await tester.pumpWidget(
          host(
            const AdaptiveScreen(title: 'Detalle', child: Text('contenido')),
          ),
        );

        expect(find.byType(CupertinoPageScaffold), findsOneWidget);
        expect(find.byType(CupertinoNavigationBar), findsOneWidget);
        expect(find.byType(AppBar), findsNothing);
        expect(find.text('Detalle'), findsOneWidget);
        expect(find.text('contenido'), findsOneWidget);
      });
    });

    testWidgets('en Android conserva Scaffold y AppBar', (tester) async {
      await withPlatform(TargetPlatform.android, () async {
        await tester.pumpWidget(
          host(
            const AdaptiveScreen(title: 'Detalle', child: Text('contenido')),
          ),
        );

        expect(find.byType(Scaffold), findsOneWidget);
        expect(find.byType(AppBar), findsOneWidget);
        expect(find.byType(CupertinoPageScaffold), findsNothing);
      });
    });

    testWidgets('el cierre modal funciona en iPhone', (tester) async {
      await withPlatform(TargetPlatform.iOS, () async {
        int closed = 0;
        await tester.pumpWidget(
          host(
            AdaptiveScreen(
              title: 'Detalle',
              onClose: () => closed++,
              child: const Text('contenido'),
            ),
          ),
        );
        await tester.tap(find.text('Cerrar'));
        await tester.pumpAndSettle();
        expect(closed, 1);
      });
    });

    testWidgets('el cierre modal funciona en Android', (tester) async {
      await withPlatform(TargetPlatform.android, () async {
        int closed = 0;
        await tester.pumpWidget(
          host(
            AdaptiveScreen(
              title: 'Detalle',
              onClose: () => closed++,
              child: const Text('contenido'),
            ),
          ),
        );
        await tester.tap(find.byIcon(Icons.close));
        await tester.pumpAndSettle();
        expect(closed, 1);
      });
    });
  });

  group('AdaptiveButton', () {
    testWidgets('en iPhone es un CupertinoButton', (tester) async {
      await withPlatform(TargetPlatform.iOS, () async {
        await tester.pumpWidget(
          host(Center(child: AdaptiveButton(label: 'Enviar', onPressed: () {}))),
        );

        expect(find.byType(CupertinoButton), findsOneWidget);
        expect(find.byType(FilledButton), findsNothing);
        expect(find.text('Enviar'), findsOneWidget);
      });
    });

    testWidgets('en Android sigue siendo un botón Material', (tester) async {
      await withPlatform(TargetPlatform.android, () async {
        await tester.pumpWidget(
          host(Center(child: AdaptiveButton(label: 'Enviar', onPressed: () {}))),
        );

        expect(find.byType(FilledButton), findsOneWidget);
        expect(find.byType(CupertinoButton), findsNothing);
      });
    });

    testWidgets('sin acción queda deshabilitado en iPhone', (tester) async {
      await withPlatform(TargetPlatform.iOS, () async {
        await tester.pumpWidget(
          host(
            const Center(
              child: AdaptiveButton(label: 'Enviar', onPressed: null),
            ),
          ),
        );

        final CupertinoButton button = tester.widget(
          find.byType(CupertinoButton),
        );
        expect(button.enabled, isFalse);
      });
    });
  });

  group('showAdaptiveNotice', () {
    testWidgets('en iPhone abre una alerta nativa, no un snackbar', (
      tester,
    ) async {
      await withPlatform(TargetPlatform.iOS, () async {
        await tester.pumpWidget(
          host(
            Builder(
              builder: (context) => Center(
                child: AdaptiveButton(
                  label: 'Avisar',
                  onPressed: () =>
                      showAdaptiveNotice(context, message: 'Falta el país'),
                ),
              ),
            ),
          ),
        );
        await tester.tap(find.text('Avisar'));
        await tester.pumpAndSettle();

        expect(find.byType(CupertinoAlertDialog), findsOneWidget);
        expect(find.text('Falta el país'), findsOneWidget);
        expect(find.byType(SnackBar), findsNothing);

        await tester.tap(find.text('Entendido'));
        await tester.pumpAndSettle();
        expect(find.byType(CupertinoAlertDialog), findsNothing);
      });
    });

    testWidgets('en Android sigue mostrando un snackbar', (tester) async {
      await withPlatform(TargetPlatform.android, () async {
        await tester.pumpWidget(
          host(
            Scaffold(
              body: Builder(
                builder: (context) => Center(
                  child: AdaptiveButton(
                    label: 'Avisar',
                    onPressed: () =>
                        showAdaptiveNotice(context, message: 'Falta el país'),
                  ),
                ),
              ),
            ),
          ),
        );
        await tester.tap(find.text('Avisar'));
        await tester.pump();

        expect(find.byType(SnackBar), findsOneWidget);
        expect(find.byType(CupertinoAlertDialog), findsNothing);
      });
    });
  });

  group('AdaptiveCard', () {
    testWidgets('en iPhone es vidrio', (tester) async {
      await withPlatform(TargetPlatform.iOS, () async {
        await tester.pumpWidget(host(const AdaptiveCard(child: Text('aviso'))));
        expect(find.byType(LiquidGlass), findsOneWidget);
        expect(find.byType(Card), findsNothing);
      });
    });

    testWidgets('en Android sigue siendo una Card', (tester) async {
      await withPlatform(TargetPlatform.android, () async {
        await tester.pumpWidget(host(const AdaptiveCard(child: Text('aviso'))));
        expect(find.byType(Card), findsOneWidget);
        expect(find.byType(LiquidGlass), findsNothing);
      });
    });
  });

  group('adaptiveRoute', () {
    test('elige la transición nativa de cada plataforma', () {
      debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
      expect(
        adaptiveRoute<void>((_) => const SizedBox.shrink()),
        isA<CupertinoPageRoute<void>>(),
      );

      debugDefaultTargetPlatformOverride = TargetPlatform.android;
      expect(
        adaptiveRoute<void>((_) => const SizedBox.shrink()),
        isA<MaterialPageRoute<void>>(),
      );
      debugDefaultTargetPlatformOverride = null;
    });
  });
}
