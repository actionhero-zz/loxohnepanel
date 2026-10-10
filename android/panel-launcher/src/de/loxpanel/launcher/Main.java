package de.loxpanel.launcher;

import android.app.Activity;
import android.os.Bundle;

/**
 * Nur fuer adb: Panel oeffnen (TbView oder Fully).
 * "--es url <URL>" speichert die Panel-URL, "--es mode tbview|fully" waehlt die Anzeige.
 */
public class Main extends Activity {
    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        boolean setUrl = getIntent().hasExtra("url");
        if (setUrl) Fully.saveUrl(this, getIntent().getStringExtra("url"));
        if (getIntent().hasExtra("mode")) Kiosk.setMode(this, getIntent().getStringExtra("mode"));
        // Neue URL (Einrichtung): sofort laden; sonst laufendes Panel nur nach vorn.
        Kiosk.openPanel(this, setUrl);
        finish();
    }
}
