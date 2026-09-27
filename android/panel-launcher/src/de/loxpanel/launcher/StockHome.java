package de.loxpanel.launcher;

import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ResolveInfo;
import android.graphics.drawable.Drawable;

import java.util.List;

/**
 * Der urspruengliche Startbildschirm des Geraets (HOME) - auf dem Shelly Wall
 * Display die Shelly-Oberflaeche, auf Tablets der normale Android-Launcher.
 * Bewusst nicht per Paketname fest verdrahtet: der unterscheidet sich je
 * Geraet/Firmware (z.B. cloud.shelly.stargate).
 */
final class StockHome {
    private StockHome() {}

    static ResolveInfo find(Context c) {
        Intent home = new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_HOME);
        List<ResolveInfo> all = c.getPackageManager().queryIntentActivities(home, 0);
        for (ResolveInfo ri : all) {
            String pkg = ri.activityInfo.packageName;
            // Uns selbst und den Android-Auswahldialog ("android"/Settings-Fallback) ueberspringen.
            if (!pkg.equals(c.getPackageName()) && !pkg.equals("android")
                    && !pkg.equals("com.android.settings")) {
                return ri;
            }
        }
        return null;
    }

    static boolean start(Context c) {
        ResolveInfo ri = find(c);
        if (ri == null) return false;
        Intent i = new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_HOME)
                .setComponent(new ComponentName(ri.activityInfo.packageName, ri.activityInfo.name))
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        try {
            c.startActivity(i);
            return true;
        } catch (RuntimeException e) {
            return false;
        }
    }

    static Drawable icon(Context c) {
        ResolveInfo ri = find(c);
        return ri != null ? ri.loadIcon(c.getPackageManager()) : null;
    }

    /** Name des Startbildschirms, z.B. "Shelly"; Fallback "Android". */
    static String label(Context c) {
        ResolveInfo ri = find(c);
        CharSequence l = ri != null ? ri.loadLabel(c.getPackageManager()) : null;
        return l != null && l.length() > 0 ? l.toString() : "Android";
    }
}
