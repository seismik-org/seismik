package com.seismik.app

import android.app.Activity
import android.content.Intent
import android.os.Bundle

/**
 * Recibe `seismik://auth/callback` al terminar el inicio de sesión en Custom Tabs.
 *
 * El filtro no se declara en MainActivity porque la pestaña del navegador queda
 * encima de ella: con `singleTop` Android crearía una segunda MainActivity, y con
 * ella un segundo motor de Flutter. Esta actividad invisible reenvía el retorno a
 * la instancia existente —cerrando de paso la pestaña— y termina.
 */
class OAuthCallbackActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val data = intent?.data
        if (data != null && MainActivity.isOAuthCallback(data)) {
            startActivity(
                Intent(this, MainActivity::class.java)
                    .setData(data)
                    .addFlags(
                        Intent.FLAG_ACTIVITY_NEW_TASK or
                            Intent.FLAG_ACTIVITY_CLEAR_TOP or
                            Intent.FLAG_ACTIVITY_SINGLE_TOP,
                    ),
            )
        }
        finish()
    }
}
