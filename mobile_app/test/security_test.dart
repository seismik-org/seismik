import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:seismik/core/security.dart';

void main() {
  test('HMAC signs timestamp dot and the exact UTF-8 body', () {
    final String signature = SeismikSecurity.hmacSha256Hex(
      secret: 'secret',
      timestamp: '1723860604.120',
      bodyBytes: utf8.encode('{"pga":0.08}'),
    );
    expect(signature, hasLength(64));
    expect(signature, matches(RegExp(r'^[0-9a-f]{64}$')));
    expect(
      signature,
      isNot(SeismikSecurity.hmacSha256Hex(
        secret: 'secret',
        timestamp: '1723860604.121',
        bodyBytes: utf8.encode('{"pga":0.08}'),
      )),
    );
  });
}
