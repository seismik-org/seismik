import 'dart:async';

import 'package:flutter/material.dart';
import 'package:wakelock_plus/wakelock_plus.dart';

import '../../data/models/seismic_event.dart';
import '../widgets/open_in_maps_button.dart';
import '../widgets/safety_steps.dart';

class AlertOverlay extends StatefulWidget {
  const AlertOverlay({required this.event, required this.onDismiss, super.key});
  final SeismicEvent event;
  final VoidCallback onDismiss;

  @override
  State<AlertOverlay> createState() => _AlertOverlayState();
}

class _AlertOverlayState extends State<AlertOverlay>
    with SingleTickerProviderStateMixin {
  late final AnimationController _flash;
  late final Timer _timer;
  int _elapsedSeconds = 0;

  @override
  void initState() {
    super.initState();
    unawaited(WakelockPlus.enable());
    _flash = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 550),
    )..repeat(reverse: true);
    _updateElapsed();
    _timer = Timer.periodic(
      const Duration(seconds: 1),
      (_) => _updateElapsed(),
    );
  }

  void _updateElapsed() {
    if (!mounted) return;
    setState(() {
      _elapsedSeconds = DateTime.now()
          .toUtc()
          .difference(widget.event.detectedAt)
          .inSeconds
          .clamp(0, 9999);
    });
  }

  @override
  void dispose() {
    _timer.cancel();
    _flash.dispose();
    unawaited(WakelockPlus.disable());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => PopScope(
    canPop: false,
    child: AnimatedBuilder(
      animation: _flash,
      builder: (BuildContext context, Widget? child) => ColoredBox(
        color: Color.lerp(
          const Color(0xFF850000),
          const Color(0xFFE00000),
          _flash.value,
        )!,
        child: child,
      ),
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 18),
          child: Column(
            children: <Widget>[
              const Icon(
                Icons.warning_amber_rounded,
                color: Colors.white,
                size: 88,
              ),
              const SizedBox(height: 12),
              const Text(
                '¡SISMO DETECTADO!\nBUSCA PROTECCIÓN',
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 34,
                  height: 1.04,
                  fontWeight: FontWeight.w900,
                ),
              ),
              const Spacer(),
              Text(
                '$_elapsedSeconds s',
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 72,
                  fontWeight: FontWeight.w200,
                ),
              ),
              const Text(
                'desde la detección de onda P',
                style: TextStyle(color: Colors.white70),
              ),
              const Spacer(),
              const SafetySteps(),
              const Spacer(),
              // La ubicación es contexto secundario: primero protegerse, y sólo
              // después mirar dónde ocurrió.
              Theme(
                data: Theme.of(context).copyWith(
                  textButtonTheme: TextButtonThemeData(
                    style: TextButton.styleFrom(
                      foregroundColor: Colors.white,
                    ),
                  ),
                ),
                child: OpenInMapsButton(event: widget.event, compact: true),
              ),
              // La acción de cierre conserva su forma en ambas plataformas: es
              // la única salida de una pantalla que aparece en una emergencia y
              // no debe depender de reconocer un control nuevo.
              SizedBox(
                width: double.infinity,
                child: FilledButton.tonalIcon(
                  onPressed: widget.onDismiss,
                  icon: const Icon(Icons.check_circle_outline),
                  label: const Text('ESTOY A SALVO · CERRAR'),
                ),
              ),
            ],
          ),
        ),
      ),
    ),
  );
}
