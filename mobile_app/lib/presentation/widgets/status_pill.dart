import 'package:flutter/material.dart';

import '../../core/theme.dart';

class StatusPill extends StatelessWidget {
  const StatusPill({required this.online, super.key});
  final bool online;

  @override
  Widget build(BuildContext context) {
    final Brightness brightness = Theme.of(context).brightness;
    final bool dark = brightness == Brightness.dark;
    final Color accent = online ? SeismikColors.emerald : SeismikColors.amber;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
      decoration: BoxDecoration(
        color: accent.withValues(alpha: dark ? 0.14 : 0.10),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: accent.withValues(alpha: dark ? 0.35 : 0.45),
          width: 0.9,
        ),
        boxShadow: <BoxShadow>[
          BoxShadow(
            color: accent.withValues(alpha: dark ? 0.12 : 0.08),
            blurRadius: 12,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(
              color: accent,
              shape: BoxShape.circle,
              boxShadow: <BoxShadow>[
                BoxShadow(
                  color: accent.withValues(alpha: 0.8),
                  blurRadius: 6,
                  spreadRadius: 1,
                ),
              ],
            ),
          ),
          const SizedBox(width: 9),
          Text(
            online
                ? 'Monitoreando red sísmica Seismik'
                : 'Reconectando con Seismik…',
            style: TextStyle(
              fontSize: 12.5,
              fontWeight: FontWeight.w600,
              color: dark ? Colors.white : const Color(0xFF1C1C1E),
              letterSpacing: -0.1,
            ),
          ),
        ],
      ),
    );
  }
}

