import 'package:flutter/material.dart';

import '../../services/in_app_browser.dart';

/// Attribution and independence notice required wherever Seismik displays
/// information issued by public geological agencies.
class GovernmentSourcesScreen extends StatelessWidget {
  const GovernmentSourcesScreen({super.key});

  static const String disclaimer =
      'Seismik es una aplicación independiente y experimental. No representa, '
      'no está afiliada a, no cuenta con aval de, ni presta servicios en nombre '
      'de ninguna entidad pública, incluido el Servicio Geológico Colombiano (SGC). '
      'No es un servicio de emergencias ni un sistema público certificado de alerta temprana.';

  static const List<_Source> _sources = <_Source>[
    _Source(
      name: 'Servicio Geológico Colombiano (SGC)',
      detail: 'Información sismológica oficial de Colombia',
      url: 'https://sismo.sgc.gov.co/',
    ),
    _Source(
      name: 'USGS Earthquake Hazards Program',
      detail: 'Fuente pública oficial de Estados Unidos',
      url: 'https://www.usgs.gov/programs/earthquake-hazards',
    ),
    _Source(
      name: 'Instituto Geofísico del Perú (IGP)',
      detail: 'Fuente oficial de Perú',
      url: 'https://censis.igp.gob.pe/',
    ),
    _Source(
      name: 'Istituto Nazionale di Geofisica e Vulcanologia (INGV)',
      detail: 'Fuente pública de Italia',
      url: 'https://terremoti.ingv.it/',
    ),
    _Source(
      name: 'GeoNet',
      detail: 'Red nacional de riesgos geológicos de Nueva Zelanda',
      url: 'https://www.geonet.org.nz/earthquake',
    ),
    _Source(
      name: 'BMKG',
      detail: 'Agencia de meteorología, climatología y geofísica de Indonesia',
      url: 'https://www.bmkg.go.id/gempabumi',
    ),
    _Source(
      name: 'Japan Meteorological Agency (JMA)',
      detail: 'Fuente oficial de Japón',
      url: 'https://www.data.jma.go.jp/multi/quake/index.html?lang=en',
    ),
    _Source(
      name: 'EMSC/CSEM',
      detail: 'Centro sismológico euro-mediterráneo; fuente complementaria',
      url: 'https://www.emsc-csem.org/',
    ),
  ];

  @override
  Widget build(BuildContext context) {
    final ColorScheme colors = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Fuentes y aviso legal')),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 28),
        children: <Widget>[
          Card(
            color: colors.errorContainer,
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Icon(
                    Icons.info_outline_rounded,
                    color: colors.onErrorContainer,
                  ),
                  const SizedBox(height: 10),
                  Text(
                    'Seismik no es una entidad pública',
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.w800,
                      color: colors.onErrorContainer,
                    ),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    disclaimer,
                    style: TextStyle(color: colors.onErrorContainer),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 18),
          Text(
            'Fuentes originales',
            style: Theme.of(
              context,
            ).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w900),
          ),
          const SizedBox(height: 4),
          const Text(
            'Los reportes pueden ser preliminares, corregirse o no estar disponibles. '
            'Abre la fuente original para confirmar cualquier información.',
          ),
          const SizedBox(height: 10),
          for (final _Source source in _sources)
            Card(
              child: ListTile(
                leading: const Icon(Icons.open_in_new_rounded),
                title: Text(source.name),
                subtitle: Text('${source.detail}\n${source.url}'),
                isThreeLine: true,
                onTap: () => _openSource(context, source),
              ),
            ),
          const SizedBox(height: 12),
          Text(
            'Las señales colaborativas y de estaciones abiertas de Seismik se muestran '
            'como preliminares; no son confirmación oficial.',
            style: TextStyle(color: colors.onSurfaceVariant),
          ),
        ],
      ),
    );
  }

  Future<void> _openSource(BuildContext context, _Source source) async {
    final bool opened = await openWebLink(Uri.parse(source.url));
    if (!opened && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('No fue posible abrir la fuente.')),
      );
    }
  }
}

class _Source {
  const _Source({required this.name, required this.detail, required this.url});

  final String name;
  final String detail;
  final String url;
}
