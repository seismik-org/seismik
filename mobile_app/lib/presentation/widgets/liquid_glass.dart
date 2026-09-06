import 'dart:ui' as ui;

import 'package:flutter/cupertino.dart';

/// Material de vidrio para la interfaz de iPhone.
///
/// Flutter 3.47 no expone la API Liquid Glass de Apple, así que este material la
/// reconstruye con las primitivas reales del motor: desenfoque del fondo, la
/// esquina superelíptica de Apple (`RSuperellipse`, no un círculo), un tinte que
/// se adapta a la luminosidad y un borde especular más brillante arriba, que es
/// lo que da la lectura de «vidrio» y no la de «panel translúcido».
///
/// Cada capa de vidrio implica una pasada de `BackdropFilter`, que es cara: usa
/// pocas y grandes en lugar de muchas pequeñas.
class LiquidGlass extends StatelessWidget {
  const LiquidGlass({
    required this.child,
    this.borderRadius = 28,
    this.blurSigma = 24,
    this.padding,
    this.opacity,
    this.showShadow = true,
    this.borderRadiusGeometry,
    super.key,
  });

  /// Variante para barras de navegación y pestañas: sin sombra, con una
  /// separación de un píxel físico como hace el sistema.
  const LiquidGlass.bar({
    required this.child,
    this.blurSigma = 28,
    this.padding,
    this.opacity,
    super.key,
  }) : borderRadius = 0,
       showShadow = false,
       borderRadiusGeometry = null;

  final Widget child;
  final double borderRadius;
  final double blurSigma;
  final EdgeInsetsGeometry? padding;

  /// Ajuste fino del tinte. Sin valor usa el tinte del sistema para el brillo
  /// actual, que es lo correcto en casi todos los casos.
  final double? opacity;
  final bool showShadow;
  final BorderRadius? borderRadiusGeometry;

  bool get _isBar => borderRadius == 0 && !showShadow;

  @override
  Widget build(BuildContext context) {
    final Brightness brightness = CupertinoTheme.brightnessOf(context);
    final bool dark = brightness == Brightness.dark;
    final double tint = opacity ?? (dark ? 0.42 : 0.62);

    // El vidrio real no es un color plano: arriba recoge más luz que abajo.
    final Gradient fill = LinearGradient(
      begin: Alignment.topCenter,
      end: Alignment.bottomCenter,
      colors: dark
          ? <Color>[
              CupertinoColors.systemGrey6.darkColor.withValues(alpha: tint + 0.10),
              CupertinoColors.systemGrey6.darkColor.withValues(alpha: tint - 0.06),
            ]
          : <Color>[
              CupertinoColors.white.withValues(alpha: tint + 0.16),
              CupertinoColors.white.withValues(alpha: tint - 0.04),
            ],
    );

    // Borde especular: casi blanco en el arco superior, casi invisible abajo.
    final Gradient rim = LinearGradient(
      begin: Alignment.topCenter,
      end: Alignment.bottomCenter,
      colors: dark
          ? <Color>[
              CupertinoColors.white.withValues(alpha: 0.34),
              CupertinoColors.white.withValues(alpha: 0.05),
            ]
          : <Color>[
              CupertinoColors.white.withValues(alpha: 0.90),
              CupertinoColors.white.withValues(alpha: 0.24),
            ],
    );

    // El reflejo del borde debe medir lo mismo en cualquier pantalla: un grosor
    // fijo en píxeles lógicos se ve grueso en un iPhone de 3x.
    final double devicePixelRatio =
        MediaQuery.maybeDevicePixelRatioOf(context) ?? 3.0;
    final double hairline = 1.5 / devicePixelRatio;

    Widget surface = DecoratedBox(
      decoration: BoxDecoration(gradient: fill),
      child: CustomPaint(
        foregroundPainter: _SpecularRimPainter(
          gradient: rim,
          radius: borderRadius,
          strokeWidth: hairline,
          bar: _isBar,
          corners: borderRadiusGeometry,
        ),
        child: padding == null ? child : Padding(padding: padding!, child: child),
      ),
    );

    surface = BackdropFilter(
      filter: ui.ImageFilter.blur(sigmaX: blurSigma, sigmaY: blurSigma),
      child: surface,
    );

    if (_isBar) return surface;

    final BorderRadius corners =
        borderRadiusGeometry ?? BorderRadius.circular(borderRadius);
    // ClipRSuperellipse dibuja la esquina continua de Apple; un ClipRRect deja
    // el «corner break» que delata que la interfaz no es nativa.
    final Widget clipped = ClipRSuperellipse(
      borderRadius: corners,
      child: surface,
    );
    if (!showShadow) return clipped;
    return DecoratedBox(
      decoration: BoxDecoration(
        borderRadius: corners,
        boxShadow: <BoxShadow>[
          BoxShadow(
            color: CupertinoColors.black.withValues(alpha: dark ? 0.44 : 0.16),
            blurRadius: 26,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: clipped,
    );
  }
}

/// Pinta el reflejo del borde por encima del contenido.
class _SpecularRimPainter extends CustomPainter {
  const _SpecularRimPainter({
    required this.gradient,
    required this.radius,
    required this.strokeWidth,
    required this.bar,
    this.corners,
  });

  final Gradient gradient;
  final double radius;
  final double strokeWidth;
  final bool bar;
  final BorderRadius? corners;

  @override
  void paint(Canvas canvas, Size size) {
    final Rect bounds = Offset.zero & size;
    final Paint paint = Paint()
      ..shader = gradient.createShader(bounds)
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidth;
    if (bar) {
      // Una barra sólo necesita el filo superior; los laterales tocan la
      // pantalla y un borde completo se vería como una caja flotante.
      canvas.drawLine(
        Offset(0, strokeWidth / 2),
        Offset(size.width, strokeWidth / 2),
        paint,
      );
      return;
    }
    final Rect inset = bounds.deflate(strokeWidth / 2);
    final RSuperellipse shape = corners == null
        ? RSuperellipse.fromRectAndRadius(inset, Radius.circular(radius))
        : RSuperellipse.fromRectAndCorners(
            inset,
            topLeft: corners!.topLeft,
            topRight: corners!.topRight,
            bottomLeft: corners!.bottomLeft,
            bottomRight: corners!.bottomRight,
          );
    canvas.drawRSuperellipse(shape, paint);
  }

  @override
  bool shouldRepaint(_SpecularRimPainter oldDelegate) =>
      oldDelegate.gradient != gradient ||
      oldDelegate.radius != radius ||
      oldDelegate.strokeWidth != strokeWidth ||
      oldDelegate.bar != bar ||
      oldDelegate.corners != corners;
}

/// Tarjeta de contenido sobre vidrio, con el espaciado que usa iOS en listas
/// agrupadas.
class LiquidGlassCard extends StatelessWidget {
  const LiquidGlassCard({
    required this.child,
    this.padding = const EdgeInsets.all(16),
    this.borderRadius = 22,
    super.key,
  });

  final Widget child;
  final EdgeInsetsGeometry padding;
  final double borderRadius;

  @override
  Widget build(BuildContext context) => LiquidGlass(
    borderRadius: borderRadius,
    blurSigma: 18,
    padding: padding,
    child: child,
  );
}
