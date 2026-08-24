import 'package:flutter/material.dart';

class StatusPill extends StatelessWidget {
  const StatusPill({required this.online, super.key});
  final bool online;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
    decoration: BoxDecoration(
      color: (online ? const Color(0xFF1ECB7B) : Colors.orange).withValues(
        alpha: 0.16,
      ),
      border: Border.all(
        color: online ? const Color(0xFF1ECB7B) : Colors.orange,
      ),
      borderRadius: BorderRadius.circular(24),
    ),
    child: Row(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Icon(
          Icons.circle,
          size: 10,
          color: online ? const Color(0xFF1ECB7B) : Colors.orange,
        ),
        const SizedBox(width: 8),
        Text(
          online
              ? 'Monitoreando red sísmica Seismik'
              : 'Reconectando con Seismik',
          style: const TextStyle(fontWeight: FontWeight.w700),
        ),
      ],
    ),
  );
}
