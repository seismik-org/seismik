import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

abstract final class MaterialYouService {
  static const MethodChannel _channel = MethodChannel(
    'com.seismik.app/material_you',
  );

  static Future<Color?> readExactAccent() async {
    if (defaultTargetPlatform != TargetPlatform.android) return null;
    try {
      final int? argb = await _channel.invokeMethod<int>('getExactAccent');
      return argb == null ? null : Color(argb);
    } on PlatformException {
      return null;
    } on MissingPluginException {
      return null;
    }
  }
}
