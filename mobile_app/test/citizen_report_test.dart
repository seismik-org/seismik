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
  });
}
