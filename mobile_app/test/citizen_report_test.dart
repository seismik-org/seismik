import 'package:flutter_test/flutter_test.dart';
import 'package:seismik/data/models/citizen_report.dart';

void main() {
  test('report result preserves agency routes and emergency guidance', () {
    final ReportResult result = ReportResult.fromMap(<String, dynamic>{
      'accepted': true,
      'duplicate': false,
      'report_id': 'report-123',
      'stored_location_precision': 'approximate',
      'emergency_action_recommended': true,
      'notice': 'not an emergency service',
      'agency_routes': <Map<String, dynamic>>[
        <String, dynamic>{
          'agency_id': 'usgs_dyfi',
          'agency_name': 'USGS Did You Feel It?',
          'official_url': 'https://earthquake.usgs.gov/data/dyfi/',
          'automatic_submission': false,
        },
      ],
    });

    expect(result.accepted, isTrue);
    expect(result.emergencyActionRecommended, isTrue);
    expect(result.locationPrecision, 'approximate');
    expect(result.agencyRoutes.single.automaticSubmission, isFalse);
    expect(result.agencyRoutes.single.agencyId, 'usgs_dyfi');
  });

  test('offline catalog offers Colombia local agency and USGS', () {
    final List<AgencyRoute> agencies = OfficialAgencyCatalog.fallbackFor(
      countryCode: 'CO',
      officialEventId: 'us7000abcd',
    );

    expect(agencies.map((item) => item.agencyId), <String>['sgc', 'usgs_dyfi']);
    expect(agencies.last.officialUrl, endsWith('/us7000abcd/tellus'));
  });
}
