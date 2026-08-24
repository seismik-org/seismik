import 'dart:convert';

import 'package:crypto/crypto.dart';

abstract final class SeismikSecurity {
  static String hmacSha256Hex({
    required String secret,
    required String timestamp,
    required List<int> bodyBytes,
  }) {
    final List<int> signedBytes = <int>[
      ...utf8.encode(timestamp),
      ...utf8.encode('.'),
      ...bodyBytes,
    ];
    return Hmac(sha256, utf8.encode(secret)).convert(signedBytes).toString();
  }
}
