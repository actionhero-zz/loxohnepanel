package de.loxpanel.launcher;

import android.app.Activity;
import android.os.Bundle;

/** App-Symbol: Fully Kiosk starten. Optional "--es url <URL>" speichert die Panel-URL. */
public class Main extends Activity {
    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        if (getIntent().hasExtra("url")) {
            Fully.saveUrl(this, getIntent().getStringExtra("url"));
        }
        Fully.start(this);
        finish();
    }
}
