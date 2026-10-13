package com.seismik.seismik_wear

import android.content.Context
import android.os.Build
import android.provider.Settings

/** Wear OS 6 uses resolved framework colors from the selected watch theme. */
object WatchDynamicColors {
    @Suppress("DiscouragedApi")
    fun read(context: Context): Map<String, Long>? {
        if (Build.VERSION.SDK_INT < 35 ||
            Settings.Global.getInt(context.contentResolver, "dynamic_color_theme_enabled", 0) != 1) return null
        val roles = listOf("primary", "on_primary", "surface", "on_surface",
            "surface_container", "on_surface_variant")
        val colors = roles.map { role ->
            // Same roles as Wear Compose Material 3, which differ from phones.
            val name = when (role) {
                "primary" -> "system_primary_fixed"
                "on_primary" -> "system_on_primary_fixed"
                "surface" -> "system_background_dark"
                else -> "system_${role}_dark"
            }
            val id = context.resources.getIdentifier(name, "color", "android")
            if (id == 0) return null
            role to (context.getColor(id).toLong() and 0xffffffffL)
        }.toMap()
        return colors
    }
}
