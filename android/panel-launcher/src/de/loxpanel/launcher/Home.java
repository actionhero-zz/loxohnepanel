package de.loxpanel.launcher;

import android.app.Activity;
import android.graphics.Color;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

/** Startbildschirm mit zwei grossen Symbolen: LoxPanel und Shelly. */
public class Home extends Activity {
    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER);
        row.setBackgroundColor(Color.rgb(0x1c, 0x1f, 0x24));

        row.addView(tile(getResources().getDrawable(R.drawable.icon), "LoxPanel", new View.OnClickListener() {
            @Override public void onClick(View v) { Fully.start(Home.this); }
        }));
        row.addView(tile(Shelly.icon(this), "Shelly", new View.OnClickListener() {
            @Override public void onClick(View v) {
                if (!Shelly.start(Home.this)) {
                    Toast.makeText(Home.this, "Shelly-Oberfläche nicht gefunden", Toast.LENGTH_LONG).show();
                }
            }
        }));
        setContentView(row);
    }

    @Override
    public void onBackPressed() {
        // Startbildschirm: "Zurueck" hat hier nichts zu schliessen.
    }

    private View tile(Drawable icon, String label, View.OnClickListener onClick) {
        LinearLayout t = new LinearLayout(this);
        t.setOrientation(LinearLayout.VERTICAL);
        t.setGravity(Gravity.CENTER);
        int pad = dp(24);
        t.setPadding(pad, pad, pad, pad);
        GradientDrawable bg = new GradientDrawable();
        bg.setColor(Color.rgb(0x2b, 0x2f, 0x36));
        bg.setCornerRadius(dp(18));
        t.setBackgroundDrawable(bg);
        t.setClickable(true);
        t.setOnClickListener(onClick);

        ImageView iv = new ImageView(this);
        if (icon != null) iv.setImageDrawable(icon);
        t.addView(iv, new LinearLayout.LayoutParams(dp(96), dp(96)));

        TextView tv = new TextView(this);
        tv.setText(label);
        tv.setTextColor(Color.WHITE);
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
