package com.seismik.seismik_wear

import androidx.wear.protolayout.ActionBuilders
import androidx.wear.protolayout.ColorBuilders.argb
import androidx.wear.protolayout.DimensionBuilders.sp
import androidx.wear.protolayout.LayoutElementBuilders
import androidx.wear.protolayout.ModifiersBuilders
import androidx.wear.protolayout.ResourceBuilders
import androidx.wear.protolayout.TimelineBuilders
import androidx.wear.tiles.RequestBuilders
import androidx.wear.tiles.TileBuilders
import androidx.wear.tiles.TileService
import com.google.common.util.concurrent.Futures
import com.google.common.util.concurrent.ListenableFuture
import com.google.common.util.concurrent.SettableFuture

/**
 * El tile «Último sismo»: un deslizamiento desde la esfera y se ve la
 * magnitud, el lugar y hace cuánto fue. Tocarlo abre la app.
 */
class LatestQuakeTileService : TileService() {
    override fun onTileRequest(requestParams: RequestBuilders.TileRequest): ListenableFuture<TileBuilders.Tile> {
        val result = SettableFuture.create<TileBuilders.Tile>()
        // Sin caché hay que ir a la red, y eso no puede pasar en el hilo principal.
        Thread {
            try {
                result.set(tile(LatestQuake.current(this)))
            } catch (error: Exception) {
                result.setException(error)
            }
        }.start()
        return result
    }

    override fun onTileResourcesRequest(
        requestParams: RequestBuilders.ResourcesRequest,
    ): ListenableFuture<ResourceBuilders.Resources> =
        Futures.immediateFuture(ResourceBuilders.Resources.Builder().setVersion(RESOURCES_VERSION).build())

    private fun tile(quake: LatestQuake.Quake?): TileBuilders.Tile =
        TileBuilders.Tile.Builder()
            .setResourcesVersion(RESOURCES_VERSION)
            // La antigüedad («hace 4 min») envejece sola: el sistema vuelve a pedir el tile.
            .setFreshnessIntervalMillis(15 * 60 * 1000L)
            .setTileTimeline(TimelineBuilders.Timeline.fromLayoutElement(layout(quake)))
            .build()

    private fun layout(quake: LatestQuake.Quake?): LayoutElementBuilders.LayoutElement {
        val open = ModifiersBuilders.Clickable.Builder()
            .setId("open")
            .setOnClick(
                ActionBuilders.LaunchAction.Builder()
                    .setAndroidActivity(
                        ActionBuilders.AndroidActivity.Builder()
                            .setPackageName(packageName)
                            .setClassName("com.seismik.seismik_wear.MainActivity")
                            .build(),
                    )
                    .build(),
            )
            .build()

        val column = LayoutElementBuilders.Column.Builder()
            .setHorizontalAlignment(LayoutElementBuilders.HORIZONTAL_ALIGN_CENTER)
            .setModifiers(ModifiersBuilders.Modifiers.Builder().setClickable(open).build())

        if (quake == null) {
            return column
                .addContent(text("SEISMIK", 12f, MUTED, bold = true))
                .addContent(text("Sin datos aún", 16f, WHITE, bold = true))
                .addContent(text("Abre la app para cargar", 12f, MUTED))
                .build()
        }
        return column
            .addContent(text("ÚLTIMO SISMO", 11f, MUTED, bold = true))
            .addContent(text(quake.magnitudeLabel, 44f, band(quake.magnitude), bold = true))
            .addContent(text(quake.place, 13f, WHITE, bold = true, maxLines = 2))
            .addContent(text(quake.ago(), 12f, MUTED))
            .build()
    }

    private fun text(
        value: String,
        size: Float,
        color: Int,
        bold: Boolean = false,
        maxLines: Int = 1,
    ): LayoutElementBuilders.Text =
        LayoutElementBuilders.Text.Builder()
            .setText(value)
            .setMaxLines(maxLines)
            .setFontStyle(
                LayoutElementBuilders.FontStyle.Builder()
                    .setSize(sp(size))
                    .setColor(argb(color))
                    .setWeight(
                        if (bold) LayoutElementBuilders.FONT_WEIGHT_BOLD
                        else LayoutElementBuilders.FONT_WEIGHT_NORMAL,
                    )
                    .build(),
            )
            .build()

    // Las mismas bandas de color que el panel de la web y la app de teléfono.
    private fun band(magnitude: Double?): Int = when {
        magnitude == null -> MUTED
        magnitude >= 7.0 -> 0xFFFF5A5F.toInt()
        magnitude >= 6.0 -> 0xFFE53935.toInt()
        magnitude >= 5.0 -> 0xFFFB8C00.toInt()
        else -> 0xFFFFB300.toInt()
    }

    private companion object {
        const val RESOURCES_VERSION = "1"
        val WHITE = 0xFFFFFFFF.toInt()
        val MUTED = 0xFF9DADC8.toInt()
    }
}
