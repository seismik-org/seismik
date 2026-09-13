package com.seismik.app

import android.content.Intent
import android.net.Uri
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    private var oauthChannel: MethodChannel? = null

    // El retorno se guarda hasta que Dart lo pida. Si Android tuvo que arrancar
    // la app para entregarlo, Dart todavía no escuchaba cuando llegó.
    private var pendingCallback: String? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        val channel = MethodChannel(flutterEngine.dartExecutor.binaryMessenger, OAUTH_CHANNEL)
        channel.setMethodCallHandler { call, result ->
            when (call.method) {
                "takePendingCallback" -> {
                    result.success(pendingCallback)
                    pendingCallback = null
                }
                else -> result.notImplemented()
            }
        }
        oauthChannel = channel
        capture(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        capture(intent)
    }

    private fun capture(received: Intent?) {
        val current = received ?: return
        val uri = current.data ?: return
        if (!isOAuthCallback(uri)) return
        pendingCallback = uri.toString()
        // Se consume para que recrear la actividad no lo entregue dos veces.
        current.data = null
        oauthChannel?.invokeMethod("callbackAvailable", null)
    }

    companion object {
        const val OAUTH_CHANNEL = "com.seismik.app/oauth"

        fun isOAuthCallback(uri: Uri): Boolean =
            uri.scheme == "seismik" && uri.host == "auth" && uri.path == "/callback"
    }
}
