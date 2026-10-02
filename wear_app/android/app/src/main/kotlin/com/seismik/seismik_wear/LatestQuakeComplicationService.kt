package com.seismik.seismik_wear

import androidx.wear.watchface.complications.data.ComplicationData
import androidx.wear.watchface.complications.data.ComplicationType
import androidx.wear.watchface.complications.data.LongTextComplicationData
import androidx.wear.watchface.complications.data.PlainComplicationText
import androidx.wear.watchface.complications.data.ShortTextComplicationData
import androidx.wear.watchface.complications.datasource.ComplicationDataSourceService
import androidx.wear.watchface.complications.datasource.ComplicationRequest

/**
 * La complicación «Último sismo» para la esfera: «M 5.1» en el formato corto y
 * «M 5.1 · lugar» en el largo.
 */
class LatestQuakeComplicationService : ComplicationDataSourceService() {
    override fun onComplicationRequest(
        request: ComplicationRequest,
        listener: ComplicationRequestListener,
    ) {
        // Puede necesitar red si la app no ha dejado caché: fuera del hilo principal.
        Thread {
            listener.onComplicationData(build(request.complicationType, LatestQuake.current(this)))
        }.start()
    }

    override fun getPreviewData(type: ComplicationType): ComplicationData? =
        build(type, LatestQuake.Quake(5.1, "Santa Cruz Islands", System.currentTimeMillis() - 12 * 60_000L))

    private fun build(type: ComplicationType, quake: LatestQuake.Quake?): ComplicationData? {
        val magnitude = quake?.let { "M ${it.magnitudeLabel}" } ?: "—"
        val description = PlainComplicationText.Builder(
            quake?.let { "Último sismo: magnitud ${it.magnitudeLabel}, ${it.place}, ${it.ago()}" }
                ?: "Último sismo: sin datos",
        ).build()
        return when (type) {
            ComplicationType.SHORT_TEXT ->
                ShortTextComplicationData.Builder(
                    PlainComplicationText.Builder(magnitude).build(),
                    description,
                ).setTitle(PlainComplicationText.Builder(quake?.ago() ?: "Seismik").build()).build()
            ComplicationType.LONG_TEXT ->
                LongTextComplicationData.Builder(
                    PlainComplicationText.Builder(quake?.let { "$magnitude · ${it.place}" } ?: "Sin datos").build(),
                    description,
                ).setTitle(PlainComplicationText.Builder("Último sismo").build()).build()
            else -> null
        }
    }
}
