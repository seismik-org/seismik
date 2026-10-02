package com.seismik.seismik_wear

import android.content.Context
import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.time.Instant
import java.time.format.DateTimeParseException
import java.util.Locale

/**
 * El último sismo, para las superficies que Flutter no dibuja: el tile y la
 * complicación de la esfera.
 *
 * Primero lee la caché que la app deja en `shared_preferences` -el mismo
 * JSON de eventos que muestra su pantalla-, así el reloj no necesita red para
 * enseñar algo. Sin caché -la app aún no se ha abierto- recurre a la Seismik
 * Always Free API, que no pide clave ni registro.
 */
object LatestQuake {
    data class Quake(val magnitude: Double?, val place: String, val originMillis: Long) {
        val magnitudeLabel: String
            get() = magnitude?.let { String.format(Locale.US, "%.1f", it) } ?: "—"

        fun ago(nowMillis: Long = System.currentTimeMillis()): String {
            val minutes = ((nowMillis - originMillis) / 60_000L).coerceAtLeast(0)
            return when {
                minutes < 1 -> "ahora"
                minutes < 60 -> "hace $minutes min"
                minutes < 24 * 60 -> "hace ${minutes / 60} h"
                else -> "hace ${minutes / (24 * 60)} d"
            }
        }
    }

    // Flutter antepone "flutter." a toda clave de shared_preferences.
    private const val PREFERENCES = "FlutterSharedPreferences"
    private const val CACHE_KEY = "flutter.wear.events"
    private const val PUBLIC_URL = "https://seismik.org/v1/public/showcase-events?limit=1"

    /** Sólo lee la caché: seguro en cualquier hilo. */
    fun cached(context: Context): Quake? {
        val raw = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)
            .getString(CACHE_KEY, null) ?: return null
        return try {
            newest(JSONArray(raw))
        } catch (_: JSONException) {
            null
        }
    }

    /** Hace red si no hay caché: llamar fuera del hilo principal. */
    fun current(context: Context): Quake? = cached(context) ?: fetchPublic()

    private fun fetchPublic(): Quake? {
        val connection = URL(PUBLIC_URL).openConnection() as HttpURLConnection
        return try {
            connection.connectTimeout = 8_000
            connection.readTimeout = 8_000
            if (connection.responseCode != 200) return null
            val body = connection.inputStream.bufferedReader().use { it.readText() }
            newest(JSONObject(body).getJSONArray("events"))
        } catch (_: IOException) {
            null
        } catch (_: JSONException) {
            null
        } finally {
            connection.disconnect()
        }
    }

    /** El más reciente; un sismo confirmado gana a una detección preliminar. */
    private fun newest(events: JSONArray): Quake? {
        var best: Quake? = null
        var bestPreliminary = true
        for (index in 0 until events.length()) {
            val item = events.optJSONObject(index) ?: continue
            val preliminary = item.optString("type") == "earthquake_candidate" ||
                item.optBoolean("preliminary", false)
            val origin = parseTime(item.optString("origin_time", item.optString("detected_at"))) ?: continue
            val quake = Quake(
                magnitude = if (item.has("magnitude") && !item.isNull("magnitude")) item.optDouble("magnitude") else null,
                place = item.optString("place").ifBlank { "Ubicación no especificada" },
                originMillis = origin,
            )
            val current = best
            val better = current == null ||
                (bestPreliminary && !preliminary) ||
                (bestPreliminary == preliminary && quake.originMillis > current.originMillis)
            if (better) {
                best = quake
                bestPreliminary = preliminary
            }
        }
        return best
    }

    private fun parseTime(value: String): Long? =
        try {
            Instant.parse(value).toEpochMilli()
        } catch (_: DateTimeParseException) {
            null
        }
}
