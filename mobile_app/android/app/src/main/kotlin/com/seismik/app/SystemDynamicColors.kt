package com.seismik.app

import android.content.Context
import android.os.Build

/** Read resolved system roles instead of reconstructing a fixed-tone scheme. */
object SystemDynamicColors {
    private val roles = listOf(
        "primary", "on_primary", "primary_container", "on_primary_container",
        "secondary", "on_secondary", "secondary_container", "on_secondary_container",
        "tertiary", "on_tertiary", "tertiary_container", "on_tertiary_container",
        "error", "on_error", "error_container", "on_error_container",
        "surface", "on_surface", "on_surface_variant", "surface_dim", "surface_bright",
        "surface_container_lowest", "surface_container_low", "surface_container",
        "surface_container_high", "surface_container_highest", "outline", "outline_variant",
        "surface_inverse", "on_surface_inverse", "primary_inverse", "scrim",
        "primary_fixed", "primary_fixed_dim", "on_primary_fixed", "on_primary_fixed_variant",
        "secondary_fixed", "secondary_fixed_dim", "on_secondary_fixed", "on_secondary_fixed_variant",
        "tertiary_fixed", "tertiary_fixed_dim", "on_tertiary_fixed", "on_tertiary_fixed_variant",
    )

    @Suppress("DiscouragedApi") // Android framework roles, not app resources subject to R8.
    fun read(context: Context): Map<String, Map<String, Long>>? {
        if (Build.VERSION.SDK_INT < 34) return null
        return listOf("light", "dark").associateWith { mode ->
            roles.mapNotNull { role ->
                // Fixed roles were introduced without a mode suffix in API 34.
                val opposite = if (mode == "light") "dark" else "light"
                val name = when (role) {
                    "surface_inverse" -> "system_surface_$opposite"
                    "on_surface_inverse" -> "system_on_surface_$opposite"
                    "primary_inverse" -> "system_primary_$opposite"
                    else -> if (role.contains("fixed")) "system_$role" else "system_${role}_$mode"
                }
                val id = context.resources.getIdentifier(name, "color", "android")
                if (id == 0) null else role to (context.getColor(id).toLong() and 0xffffffffL)
            }.toMap()
        }
    }
}
