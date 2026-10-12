import 'package:flutter/material.dart';

/// Franja fija arriba de todo mientras el modo de emergencia está activo. Toda
/// ella es el botón que abre la guía; aparece y desaparece sola con la señal.
class EmergencyBanner extends StatelessWidget {
  const EmergencyBanner({
    required this.hasSignal,
    required this.onOpen,
    super.key,
  });

  final bool hasSignal;
  final VoidCallback onOpen;

  @override
  Widget build(BuildContext context) {
    final String title = hasSignal
        ? 'Modo de emergencia activo'
        : 'Sin señal · Modo de emergencia activo';
    return Semantics(
      button: true,
      label: title,
      hint: 'Abre la guía de emergencia',
      child: Material(
        color: const Color(0xFFC62828),
        child: InkWell(
          onTap: onOpen,
          child: SafeArea(
            bottom: false,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
              child: Row(
                children: <Widget>[
                  Icon(
                    hasSignal ? Icons.bolt_rounded : Icons.signal_wifi_off,
                    color: Colors.white,
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Text(
                          title,
                          style: const TextStyle(
                            color: Colors.white,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                        const Text(
                          'Toca para abrir la guía y tus notas',
                          style: TextStyle(color: Colors.white70, fontSize: 12),
                        ),
                      ],
                    ),
                  ),
                  const Icon(Icons.chevron_right_rounded, color: Colors.white),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
