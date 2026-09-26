package de.loxpanel.launcher;

import android.content.ActivityNotFoundException;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.widget.Toast;

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

    static void start(Context c) {
        String url = c.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(KEY_URL, "");
        if (!url.isEmpty()) {
            // Fully mit der Panel-URL oeffnen (wie "am start -a VIEW -d <url>").
            Intent view = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
            view.setPackage(PKG);
            if (launch(c, view)) return;
        }
        // Ohne URL (oder falls Fully die URL nicht annimmt): normaler App-Start,
        // Fully laedt dann seine eigene Start-URL - wie "monkey -p de.ozerov.fully".
        Intent main = c.getPackageManager().getLaunchIntentForPackage(PKG);
        if (main == null || !launch(c, main)) {
            Toast.makeText(c, "Fully Kiosk ist nicht installiert", Toast.LENGTH_LONG).show();
        }
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
