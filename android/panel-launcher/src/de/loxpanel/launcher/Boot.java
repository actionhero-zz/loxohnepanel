package de.loxpanel.launcher;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Handler;
import android.os.Looper;

/** Nach dem Hochfahren Fully Kiosk starten (kurz verzoegert, bis das System bereit ist). */
public class Boot extends BroadcastReceiver {
    private static final long DELAY_MS = 8000;

    @Override
    public void onReceive(final Context c, Intent intent) {
        if (!Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction())) return;
        final PendingResult pending = goAsync();
        final Context app = c.getApplicationContext();
        new Handler(Looper.getMainLooper()).postDelayed(new Runnable() {
            @Override
            public void run() {
                try {
                    Fully.start(app);
                } finally {
                    pending.finish();
                }
            }
        }, DELAY_MS);
    }
}
