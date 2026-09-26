package de.loxpanel.launcher;

import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.graphics.drawable.Drawable;

import java.util.List;

/**
 * Die urspruengliche Shelly-Oberflaeche: der andere Startbildschirm (HOME) auf
 * dem Geraet. Bewusst nicht per Paketname fest verdrahtet - der unterscheidet
 * sich je Modell/Firmware (z.B. cloud.shelly.stargate).
 */
final class Shelly {
    private Shelly() {}

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
        PackageManager pm = c.getPackageManager();
        return ri != null ? ri.loadIcon(pm) : null;
    }
}
