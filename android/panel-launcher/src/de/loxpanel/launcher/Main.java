package de.loxpanel.launcher;

import android.app.Activity;
import android.os.Bundle;

/** App-Symbol: Fully Kiosk starten. Optional "--es url <URL>" speichert die Panel-URL. */
public class Main extends Activity {
    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        boolean setUrl = getIntent().hasExtra("url");
        if (setUrl) {
            Fully.saveUrl(this, getIntent().getStringExtra("url"));
        }
        // Neue URL (Einrichtung): sofort laden; sonst laufendes Fully nur nach vorn.
        Fully.start(this, setUrl);
        finish();
    }
}
