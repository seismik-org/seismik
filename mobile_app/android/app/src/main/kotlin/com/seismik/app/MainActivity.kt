package com.seismik.app

import android.content.Intent
import android.net.Uri
import com.google.android.gms.wearable.PutDataMapRequest
import com.google.android.gms.wearable.Wearable
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
        configureWearChannel(flutterEngine)
        capture(intent)
    }

    /**
     * Puente con el reloj emparejado. «Búsqueda de familiares» exige la sesión
     * de la cuenta, que vive cifrada en el teléfono; el reloj no puede iniciar
     * sesión en una pantalla de 4 cm. Se comparte por el Data Layer, que sólo
     * ve el reloj vinculado a este teléfono, y se borra al cerrar sesión.
     */
    private fun configureWearChannel(flutterEngine: FlutterEngine) {
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, WEAR_CHANNEL)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "publishAccount" -> {
                        val session = call.argument<String>("session")
                        if (session.isNullOrBlank()) {
                            result.error("sin-sesion", "Falta la sesión de la cuenta", null)
                        } else {
                            publishAccount(session, call.argument<String>("name"))
                            result.success(true)
                        }
                    }
                    "clearAccount" -> {
                        clearAccount()
                        result.success(true)
                    }
                    else -> result.notImplemented()
                }
            }
    }

    private fun publishAccount(session: String, name: String?) {
        val request = PutDataMapRequest.create(ACCOUNT_PATH).apply {
            dataMap.putString("session", session)
            dataMap.putString("name", name ?: "")
            // Sin una marca que cambie, el Data Layer ignora un dato idéntico
            // y el reloj no se entera de que la sesión se renovó.
            dataMap.putLong("updated_at", System.currentTimeMillis())
        }
        Wearable.getDataClient(this).putDataItem(request.asPutDataRequest().setUrgent())
    }

    private fun clearAccount() {
        Wearable.getDataClient(this).deleteDataItems(Uri.parse("wear://*$ACCOUNT_PATH"))
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
        const val WEAR_CHANNEL = "seismik/wear"
        const val ACCOUNT_PATH = "/seismik/account"
        const val OAUTH_CHANNEL = "com.seismik.app/oauth"

        fun isOAuthCallback(uri: Uri): Boolean =
            uri.scheme == "seismik" && uri.host == "auth" && uri.path == "/callback"
    }
}
