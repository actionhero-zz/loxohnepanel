package de.loxpanel.launcher;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.graphics.Color;
import android.hardware.Sensor;
import android.hardware.SensorEvent;
import android.hardware.SensorEventListener;
import android.hardware.SensorManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.provider.Settings;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.webkit.RenderProcessGoneDetail;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;

import java.util.List;

/**
 * TbView: eigene Kiosk-Ansicht fuer das LoxPanel (Ersatz fuer Fully, Fully bleibt Fallback).
 * Vollbild-WebView auf die Panel-URL, JS-Bruecke "TbView" mit den Fully-Namen
 * (turnScreenOn/Off, isScreenOn) plus Naeherung, Licht und Helligkeit.
 *
 * Schoner: schwarzes Overlay + Fensterhelligkeit minimal; die Seite laeuft weiter
 * (Klingel/Websocket). Wecken per Beruehrung oder Naeherungssensor.
 * Helligkeit nur fuer dieses Fenster (Geraeteeinstellung bleibt): Auto-Helligkeit
 * aus dem Lichtsensor (X2i: Stufen 0..16, keine Lux) mal Nachtfaktor des Panels.
 */
public class Kiosk extends Activity implements SensorEventListener {
    static final String KEY_MODE = "mode";      // "tbview" | "fully" (Standard: fully)
    private static final long RETRY_MS = 3000;
    private static final long LIGHT_HOLD_MS = 3000;   // Hysterese gegen kurze Lichtwechsel

    private final Handler ui = new Handler();
    private WebView web;
    private View saver;
    private SensorManager sm;
    private Sensor prox, light;

    // Zustand
    private boolean saverOn, panelSaver, offEnabled, near, loaded;
    private long offMs = 0;
    private int lightLevel = -1, pendingLevel = -1;
    private long pendingSince;
    private float lightMax = 16f;
    private boolean autoOn = true;
    private int minPct = 10, maxPct = 100, nightPct = 100;
    private boolean proxWake = true;
    private float shown = -2f;   // zuletzt gesetzte Fensterhelligkeit

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON
                | WindowManager.LayoutParams.FLAG_FULLSCREEN
                | WindowManager.LayoutParams.FLAG_HARDWARE_ACCELERATED);
        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.BLACK);

        web = new WebView(this);
        web.setBackgroundColor(Color.BLACK);
        web.setLayerType(View.LAYER_TYPE_HARDWARE, null);
        web.setOverScrollMode(View.OVER_SCROLL_NEVER);
        web.setVerticalScrollBarEnabled(false);
        web.setHorizontalScrollBarEnabled(false);
        web.setHapticFeedbackEnabled(false);
        web.setLongClickable(false);   // kein Textauswahl-/Kontextmenue am Wandpanel
        web.setOnLongClickListener(new View.OnLongClickListener() {
            @Override public boolean onLongClick(View v) { return true; }
        });
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setCacheMode(WebSettings.LOAD_DEFAULT);
        s.setMediaPlaybackRequiresUserGesture(false);   // Klingel-Ton, Kamera
        s.setTextZoom(100);                              // Systemschrift nicht hochskalieren
        s.setSupportZoom(false);
        s.setBuiltInZoomControls(false);
        s.setDisplayZoomControls(false);
        s.setUseWideViewPort(true);
        s.setLoadWithOverviewMode(true);
        s.setAllowFileAccess(false);
        if (Build.VERSION.SDK_INT >= 21) s.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        if (Build.VERSION.SDK_INT >= 26) {
            s.setSafeBrowsingEnabled(false);             // LAN-Seite, spart Pruefungen
            web.setRendererPriorityPolicy(WebView.RENDERER_PRIORITY_IMPORTANT, false);
        }
        s.setUserAgentString(s.getUserAgentString() + " TbView/" + version());
        if (Build.VERSION.SDK_INT >= 19) WebView.setWebContentsDebuggingEnabled(true);   // chrome://inspect ueber adb
        web.addJavascriptInterface(new Bridge(), "TbView");
        web.setWebViewClient(new Client());
        root.addView(web, new FrameLayout.LayoutParams(-1, -1));

        saver = new View(this);
        saver.setBackgroundColor(Color.BLACK);
        saver.setVisibility(View.GONE);
        root.addView(saver, new FrameLayout.LayoutParams(-1, -1));
        setContentView(root);

        sm = (SensorManager) getSystemService(SENSOR_SERVICE);
        if (sm != null) {
            // X2i: Naeherung ist ein Wake-up-Sensor -> Liste zuerst (getDefaultSensor liefert ihn nicht ueberall)
            List<Sensor> l = sm.getSensorList(Sensor.TYPE_PROXIMITY);
            prox = l.isEmpty() ? sm.getDefaultSensor(Sensor.TYPE_PROXIMITY) : l.get(0);
            light = sm.getDefaultSensor(Sensor.TYPE_LIGHT);
            if (light != null && light.getMaximumRange() > 0 && light.getMaximumRange() < 100) lightMax = light.getMaximumRange();
        }
        if (light == null) autoOn = false;
        load();
    }

    private String url() {
        return getSharedPreferences("cfg", MODE_PRIVATE).getString("url", "");
    }

    private void load() {
        String u = url();
        if (u.isEmpty()) {
            web.loadData("<body style='background:#000;color:#aaa;font:20px sans-serif;padding:40px'>"
                    + "TbView: keine Panel-URL gesetzt.<br><br>adb shell am start -n de.loxpanel.launcher/.Main --es url http://&lt;LoxBerry&gt;:8098/</body>",
                    "text/html; charset=utf-8", null);
            return;
        }
        loaded = false;
        web.loadUrl(u);
    }

    private final Runnable retry = new Runnable() {
        @Override public void run() { load(); }
    };

    private class Client extends WebViewClient {
        @Override public boolean shouldOverrideUrlLoading(WebView v, String u) { return false; }

        @Override public void onPageFinished(WebView v, String u) { loaded = true; emitState(); }

        @Override public void onReceivedError(WebView v, int code, String desc, String failingUrl) {
            // Server noch nicht da (Boot, Neustart des Containers): leise erneut versuchen
            if (failingUrl != null && failingUrl.equals(v.getUrl())) offline();
        }

        @Override public void onReceivedError(WebView v, WebResourceRequest r, WebResourceError e) {
            if (Build.VERSION.SDK_INT >= 21 && r.isForMainFrame()) offline();
        }

        @Override public boolean onRenderProcessGone(WebView v, RenderProcessGoneDetail d) {
            // Renderer abgestuerzt/beendet: Activity neu aufbauen statt App-Absturz
            recreate();
            return true;
        }
    }

    private void offline() {
        web.loadData("<body style='background:#000;color:#666;font:18px sans-serif;display:flex;align-items:center;"
                + "justify-content:center;height:90vh'>LoxPanel nicht erreichbar &ndash; neuer Versuch &hellip;</body>",
                "text/html; charset=utf-8", null);
        ui.removeCallbacks(retry);
        ui.postDelayed(retry, RETRY_MS);
    }

    @Override
    protected void onResume() {
        super.onResume();
        immersive();
        web.onResume();
        if (sm != null) {
            if (prox != null) sm.registerListener(this, prox, SensorManager.SENSOR_DELAY_UI);
            if (light != null) sm.registerListener(this, light, SensorManager.SENSOR_DELAY_NORMAL);
        }
        applyBrightness();
    }

    @Override
    protected void onPause() {
        super.onPause();
        if (sm != null) sm.unregisterListener(this);
    }

    @Override
    protected void onDestroy() {
        ui.removeCallbacksAndMessages(null);
        if (web != null) { web.destroy(); web = null; }
        super.onDestroy();
    }

    @Override public void onWindowFocusChanged(boolean f) { super.onWindowFocusChanged(f); if (f) immersive(); }

    @Override public void onBackPressed() { /* Wandpanel: kein Zurueck aus dem Kiosk */ }

    @Override
    protected void onNewIntent(Intent i) {
        super.onNewIntent(i);
        if (i != null && i.getBooleanExtra("reload", false)) load();
    }

    private void immersive() {
        getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                | View.SYSTEM_UI_FLAG_FULLSCREEN | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                | View.SYSTEM_UI_FLAG_LAYOUT_STABLE | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION);
    }

    // ---- Beruehrung: erster Tipp im Schoner weckt nur (loest nichts darunter aus) ----
    @Override
    public boolean dispatchTouchEvent(MotionEvent ev) {
        if (saverOn) {
            if (ev.getActionMasked() == MotionEvent.ACTION_DOWN) userWake();
            return true;
        }
        rearmOff();
        return super.dispatchTouchEvent(ev);
    }

    // ---- Sensoren ----
    @Override
    public void onSensorChanged(SensorEvent e) {
        if (e.sensor.getType() == Sensor.TYPE_PROXIMITY) {
            boolean n = e.values.length > 0 && e.values[0] < e.sensor.getMaximumRange();
            if (n == near) return;
            near = n;
            // Display an; ob das Dashboard schliesst, entscheidet das Panel (Ereignis "prox")
            if (near && saverOn && proxWake) { exitSaver(); rearmOff(); }
            js("prox", near ? "true" : "false");
        } else if (e.sensor.getType() == Sensor.TYPE_LIGHT) {
            int lv = Math.round(e.values[0]);
            long now = System.currentTimeMillis();
            if (lightLevel < 0 || Math.abs(lv - lightLevel) >= 3) { setLight(lv); return; }   // grosser Sprung sofort
            if (lv == lightLevel) { pendingLevel = -1; return; }
            if (lv != pendingLevel) { pendingLevel = lv; pendingSince = now; return; }
            if (now - pendingSince >= LIGHT_HOLD_MS) setLight(lv);
        }
    }

    private void setLight(int lv) {
        lightLevel = lv;
        pendingLevel = -1;
        applyBrightness();
        js("light", String.valueOf(lv));
    }

    @Override public void onAccuracyChanged(Sensor s, int a) {}

    // ---- Helligkeit ----
    /** Auto-Kurve: Stufe 0..max -> Anteil min..max (Wurzel: dunkle Raeume feiner abgestuft). */
    private float autoFraction() {
        float minF = minPct / 100f, maxF = Math.max(minF, maxPct / 100f);
        float x = Math.max(0f, Math.min(1f, lightLevel / (lightMax * 0.85f)));
        return minF + (maxF - minF) * (float) Math.sqrt(x);
    }

    /** Systemhelligkeit als Anteil, null bei automatischer Helligkeit (unbekannt). */
    private Float systemFraction() {
        try {
            if (Settings.System.getInt(getContentResolver(), Settings.System.SCREEN_BRIGHTNESS_MODE) == 1) return null;
            return Math.min(1f, Settings.System.getInt(getContentResolver(), Settings.System.SCREEN_BRIGHTNESS) / 255f);
        } catch (Settings.SettingNotFoundException ex) {
            return null;
        }
    }

    private void applyBrightness() {
        float b;
        if (saverOn) b = 0f;   // praktisch dunkel
        else {
            Float base = (autoOn && lightLevel >= 0) ? Float.valueOf(autoFraction()) : (nightPct < 100 ? systemFraction() : null);
            b = base == null ? WindowManager.LayoutParams.BRIGHTNESS_OVERRIDE_NONE
                    : Math.max(0.01f, base * nightPct / 100f);
        }
        if (Math.abs(b - shown) < 0.005f) return;
        shown = b;
        WindowManager.LayoutParams lp = getWindow().getAttributes();
        lp.screenBrightness = b;
        getWindow().setAttributes(lp);
    }

    // ---- Schoner ----
    private final Runnable goDark = new Runnable() {
        @Override public void run() { enterSaver(); }
    };

    private void rearmOff() {
        ui.removeCallbacks(goDark);
        if (offEnabled && panelSaver && !saverOn) ui.postDelayed(goDark, offMs);
    }

    private void enterSaver() {
        if (saverOn) return;
        saverOn = true;
        saver.setVisibility(View.VISIBLE);
        saver.bringToFront();
        applyBrightness();
        js("screen", "false");
    }

    private void exitSaver() {
        if (!saverOn) return;
        saverOn = false;
        saver.setVisibility(View.GONE);
        applyBrightness();
        js("screen", "true");
    }

    private void userWake() {
        exitSaver();
        rearmOff();
        // Panel schliesst seinen Schoner (wie Fully "onScreenOn")
        if (web != null) web.evaluateJavascript("try{ if(typeof wake==='function') wake(); }catch(e){}", null);
    }

    /** Ereignis an das Panel: window.lpHost._ev(name, wert) - nur wenn das Panel es kennt. */
    private void js(final String ev, final String val) {
        if (web == null || !loaded) return;
        ui.post(new Runnable() {
            @Override public void run() {
                if (web != null) web.evaluateJavascript("try{ window.lpHost&&lpHost._ev&&lpHost._ev('" + ev + "'," + val + "); }catch(e){}", null);
            }
        });
    }

    private void emitState() {
        js("prox", near ? "true" : "false");
        if (lightLevel >= 0) js("light", String.valueOf(lightLevel));
    }

    private String version() {
        try { return getPackageManager().getPackageInfo(getPackageName(), 0).versionName; }
        catch (Exception e) { return "?"; }
    }

    /** JS-Bruecke. Methoden laufen im Binder-Thread -> UI-Aenderungen per ui.post. */
    private class Bridge {
        // -- wie Fully Kiosk --
        @JavascriptInterface public void turnScreenOn() { ui.post(new Runnable() { public void run() { exitSaver(); rearmOff(); } }); }
        @JavascriptInterface public void turnScreenOff() { ui.post(new Runnable() { public void run() { enterSaver(); } }); }
        @JavascriptInterface public boolean isScreenOn() { return !saverOn; }
        @JavascriptInterface public String getDeviceId() {
            return Settings.Secure.getString(getContentResolver(), Settings.Secure.ANDROID_ID);
        }

        // -- Schoner (wie LoxKiosk) --
        /** Backlight aus n s nach Start des Panel-Schoners; 0 = nie. */
        @JavascriptInterface public void setDisplayOff(final int seconds) {
            ui.post(new Runnable() { public void run() {
                offEnabled = seconds > 0;
                offMs = seconds * 1000L;
                if (offEnabled) rearmOff(); else { ui.removeCallbacks(goDark); exitSaver(); }
            } });
        }
        /** Panel meldet seinen eigenen Schoner (Uhr/Dashboard) an/aus. */
        @JavascriptInterface public void setSaver(final boolean on) {
            ui.post(new Runnable() { public void run() {
                panelSaver = on;
                if (on) rearmOff(); else { ui.removeCallbacks(goDark); exitSaver(); }
            } });
        }

        // -- Helligkeit --
        /** Nachtfaktor in % (100 = normal). true = App dunkelt echt ab, false = Panel soll per Overlay abdunkeln. */
        @JavascriptInterface public boolean setDisplayBrightness(final int prozent) {
            final int p = Math.max(1, Math.min(100, prozent));
            boolean ok = p >= 100 || (autoOn && lightLevel >= 0) || systemFraction() != null;
            if (ok) ui.post(new Runnable() { public void run() { nightPct = p; applyBrightness(); } });
            return ok;
        }
        /** Auto-Helligkeit aus dem Lichtsensor an/aus, Bereich min..max in %. */
        @JavascriptInterface public void setAutoBrightness(final boolean on, final int minProzent, final int maxProzent) {
            ui.post(new Runnable() { public void run() {
                autoOn = on && light != null;
                minPct = Math.max(1, Math.min(100, minProzent));
                maxPct = Math.max(minPct, Math.min(100, maxProzent));
                applyBrightness();
            } });
        }
        /** Annaeherung weckt das Display (true) oder wird nur gemeldet (false). */
        @JavascriptInterface public void setProximityWake(final boolean on) {
            ui.post(new Runnable() { public void run() { proxWake = on; } });
        }

        // -- Sensoren / Geraet --
        @JavascriptInterface public boolean getProximity() { return near; }
        @JavascriptInterface public int getLightLevel() { return lightLevel; }
        @JavascriptInterface public String getDeviceInfo() {
            return "{\"app\":\"TbView\",\"ver\":\"" + version() + "\",\"model\":\"" + Build.MODEL
                    + "\",\"android\":\"" + Build.VERSION.RELEASE + "\",\"sdk\":" + Build.VERSION.SDK_INT
                    + ",\"prox\":" + (prox != null) + ",\"light\":" + (light != null)
                    + ",\"lightMax\":" + lightMax + ",\"auto\":" + autoOn + ",\"min\":" + minPct
                    + ",\"max\":" + maxPct + ",\"proxWake\":" + proxWake + "}";
        }
        @JavascriptInterface public void reload() { ui.post(new Runnable() { public void run() { load(); } }); }
    }

    /** Panel oeffnen: TbView, wenn gewaehlt, sonst Fully (Fallback). force = Seite neu laden. */
    static void openPanel(Context c, boolean force) {
        if (enabled(c)) {
            Intent i = new Intent(c, Kiosk.class);
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_REORDER_TO_FRONT);
            if (force) i.putExtra("reload", true);
            c.startActivity(i);
        } else {
            Fully.start(c, force);
        }
    }

    static boolean enabled(Context c) {
        return "tbview".equals(c.getSharedPreferences("cfg", MODE_PRIVATE).getString(KEY_MODE, "fully"));
    }

    static void setMode(Context c, String mode) {
        c.getSharedPreferences("cfg", MODE_PRIVATE).edit()
                .putString(KEY_MODE, "tbview".equals(mode) ? "tbview" : "fully").apply();
    }
}
