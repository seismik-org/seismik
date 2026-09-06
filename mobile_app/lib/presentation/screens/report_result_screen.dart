import 'package:flutter/material.dart';

import '../../data/models/citizen_report.dart';
import '../../services/in_app_browser.dart';
import '../widgets/adaptive.dart';

class ReportResultScreen extends StatelessWidget {
  const ReportResultScreen({required this.result, super.key});
  final ReportResult result;

  Future<void> _open(BuildContext context, String url) async {
    final bool opened = await openWebLink(Uri.parse(url));
    if (!opened && context.mounted) {
      await showAdaptiveNotice(
        context,
        message: 'No fue posible abrir el formulario oficial.',
      );
    }
  }

  IconData get _statusIcon {
    if (result.queuedOffline) return Icons.cloud_off_rounded;
    return result.accepted || result.duplicate
        ? Icons.check_circle
        : Icons.error;
  }

  String get _statusTitle {
    if (result.queuedOffline) return 'Reporte guardado en el teléfono';
    return result.duplicate
        ? 'Este reporte ya estaba registrado'
        : 'Gracias por reportar';
  }

  @override
  Widget build(BuildContext context) => AdaptiveScreen(
    title: result.queuedOffline ? 'Reporte guardado' : 'Reporte recibido',
    child: ListView(
      padding: const EdgeInsets.all(20),
      children: <Widget>[
        Icon(
          _statusIcon,
          size: 72,
          color: result.queuedOffline
              ? Theme.of(context).colorScheme.tertiary
              : const Color(0xFF1ECB7B),
        ),
        const SizedBox(height: 12),
        Text(
          _statusTitle,
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.headlineSmall,
        ),
        const SizedBox(height: 12),
        Text(
          result.queuedOffline
              ? result.notice
              : 'Seismik guardó el reporte con ubicación ${result.locationPrecision == 'precise' ? 'precisa' : 'aproximada'}.',
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
              child: AdaptiveButton(
                kind: AdaptiveButtonKind.tinted,
                onPressed: () => _open(context, route.officialUrl),
                icon: Icons.open_in_new,
                label: 'Abrir ${route.agencyName}',
              ),
            ),
        ],
        const SizedBox(height: 28),
        AdaptiveButton(
          icon: Icons.map_outlined,
          label: 'Volver al monitor',
          onPressed: () =>
              Navigator.of(context).popUntil((route) => route.isFirst),
        ),
      ],
    ),
  );
}
