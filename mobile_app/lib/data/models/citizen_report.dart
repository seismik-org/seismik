class AgencyRoute {
  const AgencyRoute({
    required this.agencyName,
    required this.officialUrl,
    required this.automaticSubmission,
  });

  factory AgencyRoute.fromMap(Map<String, dynamic> map) => AgencyRoute(
    agencyName: (map['agency_name'] ?? 'Agencia oficial').toString(),
    officialUrl: (map['official_url'] ?? '').toString(),
    automaticSubmission: map['automatic_submission'] == true,
  );

  final String agencyName;
  final String officialUrl;
  final bool automaticSubmission;
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
  });

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
}
