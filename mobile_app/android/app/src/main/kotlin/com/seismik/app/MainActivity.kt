package com.seismik.app

import android.os.Build
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            MATERIAL_YOU_CHANNEL,
        ).setMethodCallHandler { call, result ->
            if (call.method != "getExactAccent") {
                result.notImplemented()
                return@setMethodCallHandler
            }
            result.success(readExactMaterialYouAccent())
        }
    }

    private fun readExactMaterialYouAccent(): Long? {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) return null
        val resourceId = resources.getIdentifier(
            "system_accent1_500",
            "color",
            "android",
        )
        if (resourceId == 0) return null
        val color = resources.getColor(resourceId, theme)
        return color.toLong() and 0xFFFFFFFFL
    }

    private companion object {
        const val MATERIAL_YOU_CHANNEL = "com.seismik.app/material_you"
    }
}
