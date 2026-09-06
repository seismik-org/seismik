import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
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
  late final AnimationController _pulse;
  late final Timer _timer;
  int _elapsedSeconds = 0;

  @override
  void initState() {
    super.initState();
    unawaited(WakelockPlus.enable());
    _pulse = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1400),
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
    _pulse.dispose();
    unawaited(WakelockPlus.disable());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => PopScope(
    canPop: false,
    child: AnimatedBuilder(
      animation: _pulse,
      builder: (BuildContext context, Widget? child) {
        final double t = CurvedAnimation(
          parent: _pulse,
          curve: Curves.easeInOut,
        ).value;
        return DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: <Color>[
                Color.lerp(
                  const Color(0xFF380007),
                  const Color(0xFF6B0211),
                  t,
                )!,
                const Color(0xFF140003),
              ],
            ),
          ),
          child: child,
        );
      },
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 18),
          child: Column(
            children: <Widget>[
              const SizedBox(height: 8),
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.12),
                  shape: BoxShape.circle,
                  border: Border.all(
                    color: Colors.white.withValues(alpha: 0.25),
                    width: 1.2,
                  ),
                  boxShadow: <BoxShadow>[
                    BoxShadow(
                      color: const Color(0xFFFF3B30).withValues(alpha: 0.35),
                      blurRadius: 30,
                      spreadRadius: 4,
                    ),
                  ],
                ),
                child: const Icon(
                  CupertinoIcons.exclamationmark_triangle_fill,
                  color: Colors.white,
                  size: 48,
                ),
              ),
              const SizedBox(height: 14),
              const Text(
                '¡SISMO DETECTADO!',
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 30,
                  height: 1.1,
                  fontWeight: FontWeight.w900,
                  letterSpacing: -0.5,
                ),
              ),
              const SizedBox(height: 4),
              const Text(
                'BUSCA PROTECCIÓN INMEDIATA',
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: Color(0xFFFF9E9E),
                  fontSize: 15,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 0.8,
                ),
              ),
              const Spacer(),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 36, vertical: 16),
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.10),
                  borderRadius: BorderRadius.circular(28),
                  border: Border.all(
                    color: Colors.white.withValues(alpha: 0.22),
                    width: 1.0,
                  ),
                  boxShadow: const <BoxShadow>[
                    BoxShadow(
                      color: Color(0x40000000),
                      blurRadius: 16,
                      offset: Offset(0, 6),
                    ),
                  ],
                ),
                child: Column(
                  children: <Widget>[
                    Text(
                      '$_elapsedSeconds s',
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 64,
                        fontWeight: FontWeight.w200,
                        letterSpacing: -1.5,
                        height: 1,
                      ),
                    ),
                    const SizedBox(height: 4),
                    const Text(
                      'desde la detección de onda P',
                      style: TextStyle(
                        color: Colors.white70,
                        fontSize: 13,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ],
                ),
              ),
              const Spacer(),
              const SafetySteps(),
              const Spacer(),
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
              const SizedBox(height: 8),
              SizedBox(
                width: double.infinity,
                height: 52,
                child: CupertinoButton(
                  color: Colors.white.withValues(alpha: 0.22),
                  borderRadius: BorderRadius.circular(26),
                  onPressed: () {
                    unawaited(HapticFeedback.mediumImpact());
                    widget.onDismiss();
                  },
                  child: const Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: <Widget>[
                      Icon(CupertinoIcons.checkmark_circle, color: Colors.white, size: 20),
                      SizedBox(width: 8),
                      Text(
                        'ESTOY A SALVO · CERRAR',
                        style: TextStyle(
                          color: Colors.white,
                          fontSize: 15,
                          fontWeight: FontWeight.w700,
                          letterSpacing: 0.4,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    ),
  );
}

