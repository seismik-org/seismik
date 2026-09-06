class AgencyRoute {
  const AgencyRoute({
    required this.agencyId,
    required this.agencyName,
    required this.officialUrl,
    required this.automaticSubmission,
    this.countryCode,
  });

  factory AgencyRoute.fromMap(Map<String, dynamic> map) => AgencyRoute(
    agencyId: (map['agency_id'] ?? '').toString(),
    agencyName: (map['agency_name'] ?? 'Agencia oficial').toString(),
    officialUrl: (map['official_url'] ?? '').toString(),
    automaticSubmission: map['automatic_submission'] == true,
    countryCode: map['country_code']?.toString(),
  );

  final String agencyId;
  final String agencyName;
  final String officialUrl;
  final bool automaticSubmission;
  final String? countryCode;
}

abstract final class OfficialAgencyCatalog {
  static List<AgencyRoute> fallbackFor({
    required String countryCode,
    String? officialEventId,
  }) {
    final List<AgencyRoute> agencies = <AgencyRoute>[];
    if (countryCode.toUpperCase() == 'CO') {
      agencies.add(
        const AgencyRoute(
          agencyId: 'sgc',
          agencyName: 'Servicio Geológico Colombiano',
          officialUrl: 'https://sismosentido.sgc.gov.co/',
          automaticSubmission: false,
          countryCode: 'CO',
        ),
      );
    }
    final bool safeEventId =
        officialEventId != null &&
        RegExp(r'^[A-Za-z0-9_-]+$').hasMatch(officialEventId);
    agencies.add(
      AgencyRoute(
        agencyId: 'usgs_dyfi',
        agencyName: 'USGS Did You Feel It?',
        officialUrl: safeEventId
            ? 'https://earthquake.usgs.gov/earthquakes/eventpage/'
                  '$officialEventId/tellus'
            : 'https://earthquake.usgs.gov/data/dyfi/',
        automaticSubmission: false,
      ),
    );
    return agencies;
  }
}

class ReportResult {
  const ReportResult({
    required this.accepted,
    required this.duplicate,
    required this.reportId,
    required this.locationPrecision,
    required this.emergencyActionRecommended,
    required this.agencyRoutes,
    required this.notice,
    this.queuedOffline = false,
  });

  /// Reporte guardado en el dispositivo porque no había conexión.
  ///
  /// Se conserva el `report_id` para que, al reenviarlo, el servidor lo
  /// reconozca como el mismo reporte y no lo duplique.
  factory ReportResult.queued({
    required String reportId,
    required String locationPrecision,
    required bool emergencyActionRecommended,
    List<AgencyRoute> agencyRoutes = const <AgencyRoute>[],
  }) => ReportResult(
    accepted: false,
    duplicate: false,
    reportId: reportId,
    locationPrecision: locationPrecision,
    emergencyActionRecommended: emergencyActionRecommended,
    agencyRoutes: agencyRoutes,
    notice:
        'Sin conexión: el reporte quedó guardado en el teléfono y se enviará '
        'automáticamente cuando vuelva la red.',
    queuedOffline: true,
  );

  factory ReportResult.fromMap(Map<String, dynamic> map) => ReportResult(
    accepted: map['accepted'] == true,
    duplicate: map['duplicate'] == true,
    reportId: (map['report_id'] ?? '').toString(),
    locationPrecision: (map['stored_location_precision'] ?? 'approximate')
        .toString(),
    emergencyActionRecommended: map['emergency_action_recommended'] == true,
    agencyRoutes: (map['agency_routes'] as List<dynamic>? ?? <dynamic>[])
        .whereType<Map<String, dynamic>>()
        .map(AgencyRoute.fromMap)
        .toList(growable: false),
    notice: (map['notice'] ?? '').toString(),
  );

  final bool accepted;
  final bool duplicate;
  final String reportId;
  final String locationPrecision;
  final bool emergencyActionRecommended;
  final List<AgencyRoute> agencyRoutes;
  final String notice;
  final bool queuedOffline;
}
