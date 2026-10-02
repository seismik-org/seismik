package com.seismik.seismik_wear

import android.content.ComponentName
import android.net.Uri
import android.view.InputDevice
import android.view.MotionEvent
import android.view.ViewConfiguration
import androidx.wear.tiles.TileService
import androidx.wear.watchface.complications.datasource.ComplicationDataSourceUpdateRequester
import com.google.android.gms.wearable.DataMapItem
import com.google.android.gms.wearable.Wearable
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.EventChannel
import io.flutter.plugin.common.MethodChannel

/**
 * La corona del reloj envía eventos que Flutter no entiende por su cuenta:
 * llegan como desplazamiento desde `SOURCE_ROTARY_ENCODER`, no como gesto
 * táctil. Aquí se traducen a píxeles y se pasan a Dart, que mueve la lista.
 */
class MainActivity : FlutterActivity() {
    private var rotary: EventChannel.EventSink? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        EventChannel(flutterEngine.dartExecutor.binaryMessenger, ROTARY_CHANNEL)
            .setStreamHandler(
                object : EventChannel.StreamHandler {
                    override fun onListen(arguments: Any?, events: EventChannel.EventSink?) {
                        rotary = events
                    }

                    override fun onCancel(arguments: Any?) {
                        rotary = null
                    }
                },
            )
        configureAccountChannel(flutterEngine)
    }

    /**
     * La sesión de la cuenta la publica el teléfono por el Data Layer: el reloj
     * no puede iniciar sesión en su pantalla. Sin teléfono emparejado o con la
     * sesión cerrada, devuelve `null` y la app lo explica.
     */
    private fun configureAccountChannel(flutterEngine: FlutterEngine) {
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, ACCOUNT_CHANNEL)
            .setMethodCallHandler { call, result ->
                if (call.method == "refreshSurfaces") {
                    refreshSurfaces()
                    result.success(null)
                    return@setMethodCallHandler
                }
                if (call.method != "accountSession") {
                    result.notImplemented()
                    return@setMethodCallHandler
                }
                Wearable.getDataClient(this)
                    .getDataItems(Uri.parse("wear://*$ACCOUNT_PATH"))
                    .addOnSuccessListener { items ->
                        var session: String? = null
                        var name: String? = null
                        var newest = Long.MIN_VALUE
                        for (item in items) {
                            val map = DataMapItem.fromDataItem(item).dataMap
                            val updatedAt = map.getLong("updated_at")
                            if (updatedAt >= newest) {
                                newest = updatedAt
                                session = map.getString("session")
                                name = map.getString("name")
                            }
                        }
                        items.release()
                        result.success(
                            if (session.isNullOrBlank()) {
                                null
                            } else {
                                mapOf("session" to session, "name" to name)
                            },
                        )
                    }
                    .addOnFailureListener { error ->
                        result.error("sin-datos", error.message, null)
                    }
            }
    }

    /**
     * Cuando la app baja sismos nuevos, el tile y la complicación de la esfera
     * se enteran en el momento en vez de esperar a su siguiente ciclo.
     */
    private fun refreshSurfaces() {
        TileService.getUpdater(this).requestUpdate(LatestQuakeTileService::class.java)
        ComplicationDataSourceUpdateRequester
            .create(this, ComponentName(this, LatestQuakeComplicationService::class.java))
            .requestUpdateAll()
    }

    // `dispatchGenericMotionEvent` y no `onGenericMotionEvent`: la corona sólo
    // llega a la vista con el foco, y la superficie de Flutter no siempre lo
    // tiene. Aquí se ve el evento antes de repartirlo.
    override fun dispatchGenericMotionEvent(event: MotionEvent): Boolean {
        if (event.action == MotionEvent.ACTION_SCROLL &&
            event.isFromSource(InputDevice.SOURCE_ROTARY_ENCODER)
        ) {
            val sink = rotary
            if (sink != null) {
                // Girar hacia adelante baja por la lista: el signo del eje es
                // el contrario del desplazamiento en pantalla.
                val delta = -event.getAxisValue(MotionEvent.AXIS_SCROLL) *
                    ViewConfiguration.get(this).scaledVerticalScrollFactor
                sink.success(delta.toDouble())
                return true
            }
        }
        return super.dispatchGenericMotionEvent(event)
    }

    private companion object {
        const val ROTARY_CHANNEL = "seismik/rotary"
        const val ACCOUNT_CHANNEL = "seismik/wear"
        const val ACCOUNT_PATH = "/seismik/account"
    }
}
