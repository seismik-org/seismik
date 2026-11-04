import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:seismik/services/api_client.dart';
import 'package:seismik/services/service_status.dart';

void main() {
  final now = DateTime.utc(2026, 11, 2, 12);
  http.Response status(bool available, {DateTime? checked}) => http.Response(
    jsonEncode({
      'checked_at': (checked ?? now).toIso8601String(),
      'services': {'api': available, 'web': true, 'developers': true},
    }),
    200,
  );
  ServiceStatusClient monitor(http.Client client) =>
      ServiceStatusClient(client: client, clock: () => now);

  test(
    'confirmed API outage is distinguished from a likely connection problem',
    () async {
      for (final available in [true, false]) {
        final client = MockClient((request) async {
          expect(
            request.url.toString(),
            'https://status.seismik.org/api/status',
          );
          expect(request.url.hasQuery, isFalse);
          expect(
            request.headers.keys.any(
              (key) =>
                  key.toLowerCase().contains('session') ||
                  key.toLowerCase() == 'authorization',
            ),
            isFalse,
          );
          return status(available);
        });
        final result = await monitor(client).diagnose(hasSignal: true);
        expect(
          result.problem,
          available
              ? ConnectionProblem.connectionLikely
              : ConnectionProblem.service,
        );
        if (available) expect(result.message, contains('no está confirmada'));
      }
    },
  );

  test(
    'an endpoint 503 remains a service problem even when global status is green',
    () async {
      final result = await monitor(
        MockClient((_) async => status(true)),
      ).diagnose(hasSignal: true, httpStatus: 503);
      expect(result.problem, ConnectionProblem.service);
      expect(result.message, contains('fallo parcial'));
    },
  );

  test('missing network does not make a status request', () async {
    final result = await monitor(
      MockClient((_) async => throw StateError('No request expected')),
    ).diagnose(hasSignal: false);
    expect(result.problem, ConnectionProblem.offline);
  });

  test(
    'unreachable, malformed, stale or future status stays unknown',
    () async {
      for (final response in [
        http.Response('unavailable', 503),
        http.Response('<html>portal</html>', 200),
        status(true, checked: now.subtract(const Duration(minutes: 3))),
        status(false, checked: now.add(const Duration(minutes: 1))),
        http.Response('{"services":{"api":"true"}}', 200),
      ]) {
        expect(
          (await monitor(
            MockClient((_) async => response),
          ).diagnose(hasSignal: true)).problem,
          ConnectionProblem.unknown,
        );
      }
      expect(
        (await monitor(
          MockClient((_) async => throw const SocketException('offline')),
        ).diagnose(hasSignal: true)).problem,
        ConnectionProblem.unknown,
      );
    },
  );

  test(
    'simultaneous failures share a probe and retries are bounded by a short cache',
    () async {
      var clock = now;
      var requests = 0;
      final barrier = Completer<http.Response>();
      final service = ServiceStatusClient(
        clock: () => clock,
        client: MockClient((_) {
          requests++;
          return requests == 1
              ? barrier.future
              : Future.value(status(true, checked: clock));
        }),
      );
      final first = service.diagnose(hasSignal: true);
      final second = service.diagnose(hasSignal: true);
      await Future<void>.delayed(Duration.zero);
      expect(requests, 1);
      barrier.complete(status(false));
      expect((await first).problem, ConnectionProblem.service);
      await second;
      await service.diagnose(hasSignal: true);
      expect(requests, 1);
      clock = clock.add(const Duration(seconds: 46));
      expect(
        (await service.diagnose(hasSignal: true)).problem,
        ConnectionProblem.connectionLikely,
      );
      expect(requests, 2);
    },
  );

  test(
    'authentication and message limits are translated without blaming connectivity',
    () async {
      final api = ApiClient(
        httpClient: MockClient(
          (_) async => throw StateError('No status request expected'),
        ),
      );
      for (final error in [
        const SeismikApiException('Account session expired', 401),
        const SeismikApiException('Wait before sending another message', 429),
        const SeismikApiException(
          'Family message recipient is no longer available',
          404,
        ),
      ]) {
        final result = await api.diagnoseFailure(error);
        expect(result.problem, ConnectionProblem.request);
        expect(result.message, isNot(contains('SeismikApiException')));
        expect(result.message, isNot(contains(error.message)));
      }
      expect(
        const SeismikApiException(
          'Account session expired',
          401,
        ).isAccountSessionRejected,
        isTrue,
      );
      expect(
        const SeismikApiException('Account session expired', 401).toString(),
        contains('sesión venció'),
      );
      api.close();
    },
  );

  test(
    'known family recovery is explained without probing the network',
    () async {
      final api = ApiClient(
        httpClient: MockClient(
          (_) async => throw StateError('No status request expected'),
        ),
      );
      final result = await api.diagnoseFailure(
        const SeismikApiException('Family data recovery in progress', 503),
      );
      expect(result.problem, ConnectionProblem.service);
      expect(result.message, contains('temporalmente suspendidos'));
      expect(result.message, contains('No crees otro círculo'));
      api.close();
    },
  );
}
