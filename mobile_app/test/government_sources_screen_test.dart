import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seismik/presentation/screens/government_sources_screen.dart';

void main() {
  testWidgets('shows independence notice and current public source URLs', (
    WidgetTester tester,
  ) async {
    tester.view.physicalSize = const Size(1000, 3000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(const MaterialApp(home: GovernmentSourcesScreen()));
    expect(find.text(GovernmentSourcesScreen.disclaimer), findsOneWidget);
    const List<String> urls = <String>[
      'https://sismo.sgc.gov.co/',
      'https://www.usgs.gov/programs/earthquake-hazards',
      'https://censis.igp.gob.pe/',
      'https://terremoti.ingv.it/',
      'https://www.geonet.org.nz/earthquake',
      'https://www.bmkg.go.id/gempabumi',
      'https://www.data.jma.go.jp/multi/quake/index.html?lang=en',
      'https://www.emsc-csem.org/',
    ];
    for (final String url in urls) {
      final Finder source = find.textContaining(url);
      expect(source, findsOneWidget);
    }
  });
}
