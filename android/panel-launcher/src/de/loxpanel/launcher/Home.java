package de.loxpanel.launcher;

import android.app.Activity;
import android.graphics.Color;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.os.Handler;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

/**
 * Startbildschirm mit zwei grossen Symbolen: LoxPanel und der urspruengliche
 * Startbildschirm. Startet Fully nach AUTOSTART_S Sekunden von selbst (nach
 * Boot, Fully-Absturz oder Verlassen von Fully); jeder Tipp bricht das ab.
 */
public class Home extends Activity {
    private static final int AUTOSTART_S = 10;
    // Farben wie LoxPanel-Theme "Bunt"
    private static final int BG = 0xff0d0f1a, TILE = 0xff262a45, TEXT = 0xffffffff, MUTED = 0xff9ea5c4;

    private final Handler handler = new Handler();
    private TextView countdown;
    private int left;

    private final Runnable tick = new Runnable() {
        @Override public void run() {
            if (left <= 0) {
                stopCountdown();
                Fully.start(Home.this, false);
                return;
            }
            countdown.setText("LoxPanel startet in " + left + " s · Tippen bricht ab");
            left--;
            handler.postDelayed(this, 1000);
        }
    };

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER);

        row.addView(tile(getResources().getDrawable(R.drawable.icon), "LoxPanel", new View.OnClickListener() {
            @Override public void onClick(View v) { Fully.start(Home.this, false); }
        }));
        row.addView(tile(StockHome.icon(this), StockHome.label(this), new View.OnClickListener() {
            @Override public void onClick(View v) {
                if (!StockHome.start(Home.this)) {
                    Toast.makeText(Home.this, "Ursprünglicher Startbildschirm nicht gefunden", Toast.LENGTH_LONG).show();
                }
            }
        }));

        countdown = new TextView(this);
        countdown.setTextColor(MUTED);
        countdown.setTextSize(TypedValue.COMPLEX_UNIT_SP, 14);
        countdown.setGravity(Gravity.CENTER);
        countdown.setPadding(0, dp(28), 0, 0);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setGravity(Gravity.CENTER);
        root.setBackgroundColor(BG);
        root.addView(row);
        root.addView(countdown);
        setContentView(root);
    }

    @Override
    protected void onResume() {
        super.onResume();
        // Bei jedem Erscheinen neu zaehlen (Boot, Absturz/Verlassen von Fully).
        if (getPackageManager().getLaunchIntentForPackage(Fully.PKG) == null) {
            countdown.setText("");   // ohne Fully kein Autostart
            return;
        }
        left = AUTOSTART_S;
        handler.removeCallbacks(tick);
        tick.run();
    }

    @Override
    protected void onPause() {
        stopCountdown();
        super.onPause();
    }

    @Override
    public boolean dispatchTouchEvent(MotionEvent ev) {
        // Jeder Tipp bricht den Autostart ab; Tipp selbst wirkt normal weiter.
        if (ev.getActionMasked() == MotionEvent.ACTION_DOWN) stopCountdown();
        return super.dispatchTouchEvent(ev);
    }

    @Override
    public void onBackPressed() {
        // Startbildschirm: "Zurueck" hat hier nichts zu schliessen.
    }

    private void stopCountdown() {
        handler.removeCallbacks(tick);
        if (countdown != null) countdown.setText("");
    }

    private View tile(Drawable icon, String label, View.OnClickListener onClick) {
        LinearLayout t = new LinearLayout(this);
        t.setOrientation(LinearLayout.VERTICAL);
        t.setGravity(Gravity.CENTER);
        int pad = dp(24);
        t.setPadding(pad, pad, pad, pad);
        GradientDrawable bg = new GradientDrawable();
        bg.setColor(TILE);
        bg.setCornerRadius(dp(22));
        t.setBackgroundDrawable(bg);
        t.setClickable(true);
        t.setOnClickListener(onClick);

        ImageView iv = new ImageView(this);
        if (icon != null) iv.setImageDrawable(icon);
        t.addView(iv, new LinearLayout.LayoutParams(dp(96), dp(96)));

        TextView tv = new TextView(this);
        tv.setText(label);
        tv.setTextColor(TEXT);
        tv.setTextSize(TypedValue.COMPLEX_UNIT_SP, 20);
        tv.setGravity(Gravity.CENTER);
        tv.setPadding(0, dp(12), 0, 0);
        t.addView(tv);

        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(dp(200), dp(200));
        lp.setMargins(dp(20), 0, dp(20), 0);
        t.setLayoutParams(lp);
        return t;
    }

    private int dp(int v) {
        return (int) TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v, getResources().getDisplayMetrics());
    }
}
