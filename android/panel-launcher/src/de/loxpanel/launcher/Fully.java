package de.loxpanel.launcher;

import android.app.ActivityManager;
import android.app.usage.UsageEvents;
import android.app.usage.UsageStatsManager;
import android.content.ActivityNotFoundException;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Build;
import android.os.SystemClock;
import android.widget.Toast;

import java.util.List;

/** Startet Fully Kiosk - mit gespeicherter URL oder mit dessen eigener Start-URL. */
final class Fully {
    static final String PKG = "de.ozerov.fully";
    private static final String PREFS = "cfg";
    private static final String KEY_URL = "url";

    private Fully() {}

    /** URL merken (per adb: am start -n de.loxpanel.launcher/.Main --es url http://...). "" = loeschen. */
    static void saveUrl(Context c, String url) {
        SharedPreferences.Editor e = c.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit();
        if (url == null || url.trim().isEmpty()) e.remove(KEY_URL); else e.putString(KEY_URL, url.trim());
        e.apply();
    }

    /** force: URL immer neu laden (Einrichtung per adb), sonst laufendes Fully nur nach vorn holen. */
    static void start(Context c, boolean force) {
        String url = c.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(KEY_URL, "");
        if (!url.isEmpty() && (force || !isRunning(c))) {
            // Fully mit der Panel-URL oeffnen (wie "am start -a VIEW -d <url>") - laedt die Seite neu.
            Intent view = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
            view.setPackage(PKG);
            if (launch(c, view)) return;
        }
        // App-Start wie "monkey -p de.ozerov.fully": laeuft Fully, kommt es
        // unveraendert nach vorn, sonst laedt es seine eigene Start-URL.
        Intent main = c.getPackageManager().getLaunchIntentForPackage(PKG);
        if (main == null || !launch(c, main)) {
            Toast.makeText(c, "Fully Kiosk ist nicht installiert", Toast.LENGTH_LONG).show();
        }
    }

    /**
     * Laeuft Fully schon? Android verraet fremde Prozesse nicht direkt:
     * bis 7.x ueber die laufenden Dienste, ab 8 ueber die Nutzungsstatistik
     * (Recht setzt der Server per "appops set ... GET_USAGE_STATS allow").
     * Unbekannt = false -> URL wird geladen (sicherer Weg, wie bisher).
     */
    static boolean isRunning(Context c) {
        try {
            ActivityManager am = (ActivityManager) c.getSystemService(Context.ACTIVITY_SERVICE);
            List<ActivityManager.RunningServiceInfo> svcs = am.getRunningServices(200);
            if (svcs != null) {
                for (ActivityManager.RunningServiceInfo s : svcs) {
                    if (PKG.equals(s.service.getPackageName())) return true;
                }
            }
        } catch (RuntimeException ignored) {
        }
        return usedSinceBoot(c);
    }

    /** Fully seit dem Booten im Vordergrund gewesen (Nutzungsstatistik, ohne Recht leer). */
    private static boolean usedSinceBoot(Context c) {
        if (Build.VERSION.SDK_INT < 21) return false;   // API erst ab Android 5
        try {
            UsageStatsManager usm = (UsageStatsManager) c.getSystemService(Context.USAGE_STATS_SERVICE);
            if (usm == null) return false;
            long now = System.currentTimeMillis();
            UsageEvents ev = usm.queryEvents(now - SystemClock.elapsedRealtime(), now);
            UsageEvents.Event e = new UsageEvents.Event();
            while (ev != null && ev.hasNextEvent()) {
                ev.getNextEvent(e);
                if (PKG.equals(e.getPackageName()) && e.getEventType() == UsageEvents.Event.MOVE_TO_FOREGROUND) {
                    return true;
                }
            }
        } catch (RuntimeException ignored) {
        }
        return false;
    }

    private static boolean launch(Context c, Intent i) {
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_RESET_TASK_IF_NEEDED);
        try {
            c.startActivity(i);
            return true;
        } catch (ActivityNotFoundException | SecurityException e) {
            return false;
        }
    }
}
