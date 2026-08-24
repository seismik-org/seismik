import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../data/models/citizen_report.dart';

class ReportResultScreen extends StatelessWidget {
  const ReportResultScreen({required this.result, super.key});
  final ReportResult result;

  Future<void> _open(BuildContext context, String url) async {
    final bool opened = await launchUrl(
      Uri.parse(url),
      mode: LaunchMode.externalApplication,
    );
    if (!opened && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('No fue posible abrir el formulario oficial.'),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Reporte recibido')),
    body: ListView(
      padding: const EdgeInsets.all(20),
      children: <Widget>[
        Icon(
          result.accepted || result.duplicate
              ? Icons.check_circle
              : Icons.error,
          size: 72,
          color: const Color(0xFF1ECB7B),
        ),
        const SizedBox(height: 12),
        Text(
          result.duplicate
              ? 'Este reporte ya estaba registrado'
              : 'Gracias por reportar',
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.headlineSmall,
        ),
        const SizedBox(height: 12),
        Text(
          'Seismik guardó el reporte con ubicación ${result.locationPrecision == 'precise' ? 'precisa' : 'aproximada'}.',
          textAlign: TextAlign.center,
        ),
        if (result.emergencyActionRecommended) ...<Widget>[
          const SizedBox(height: 20),
          const Card(
            color: Color(0xFF7A1717),
            child: Padding(
              padding: EdgeInsets.all(16),
              child: Text(
                'PELIGRO POSIBLE: este reporte no llama a emergencias. Sal a un lugar seguro si puedes y contacta ahora al número local de emergencias.',
                style: TextStyle(fontWeight: FontWeight.w800),
              ),
            ),
          ),
        ],
        if (result.agencyRoutes.isNotEmpty) ...<Widget>[
          const SizedBox(height: 24),
          Text(
            'También puedes informar a una agencia oficial',
            style: Theme.of(context).textTheme.titleLarge,
          ),
          const SizedBox(height: 8),
          const Text(
            'Por seguridad y consentimiento, Seismik no envió datos automáticamente. Cada botón abre el formulario oficial para que lo revises y completes.',
          ),
          const SizedBox(height: 12),
          for (final route in result.agencyRoutes)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: FilledButton.tonalIcon(
                onPressed: () => _open(context, route.officialUrl),
                icon: const Icon(Icons.open_in_new),
                label: Text('Abrir ${route.agencyName}'),
              ),
            ),
        ],
        const SizedBox(height: 28),
        FilledButton(
          onPressed: () =>
              Navigator.of(context).popUntil((route) => route.isFirst),
          child: const Text('Volver al monitor'),
        ),
      ],
    ),
  );
}
