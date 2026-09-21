import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// Un único flujo de la corona para toda la app.
///
/// Cada `receiveBroadcastStream` abre su propio canal con el lado nativo, y el
/// segundo le quitaría el sitio al primero: al cerrar Familia, la lista de
/// sismos se quedaría sin corona. Con un flujo compartido, el nativo ve una
/// sola suscripción por más pantallas que escuchen.
final Stream<dynamic> rotaryEvents = const EventChannel(
  'seismik/rotary',
).receiveBroadcastStream();

/// Mueve `controller` con la corona mientras esta pantalla sea la de encima.
class RotaryScroll extends StatefulWidget {
  const RotaryScroll({
    required this.controller,
    required this.child,
    this.events,
    super.key,
  });

  final ScrollController controller;
  final Widget child;

  /// Sólo las pruebas lo cambian; en el reloj es el canal nativo.
  final Stream<dynamic>? events;

  @override
  State<RotaryScroll> createState() => _RotaryScrollState();
}

class _RotaryScrollState extends State<RotaryScroll> {
  StreamSubscription<dynamic>? _subscription;

  @override
  void initState() {
    super.initState();
    _subscription = (widget.events ?? rotaryEvents).listen(_onRotary);
  }

  @override
  void dispose() {
    unawaited(_subscription?.cancel());
    super.dispose();
  }

  void _onRotary(dynamic delta) {
    if (delta is! num || !widget.controller.hasClients) return;
    // Con Familia abierta, la lista de detrás no debe moverse sola.
    if (!(ModalRoute.of(context)?.isCurrent ?? true)) return;
    final ScrollPosition position = widget.controller.position;
    final double target = (position.pixels + delta.toDouble()).clamp(
      position.minScrollExtent,
      position.maxScrollExtent,
    );
    if (target == position.pixels) return;
    widget.controller.jumpTo(target);
  }

  @override
  Widget build(BuildContext context) => widget.child;
}
