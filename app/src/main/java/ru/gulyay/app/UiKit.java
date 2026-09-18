package ru.gulyay.app;

import android.content.Context;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.TextView;

final class UiKit {
    static final int GREEN = 0xFF19C463;
    static final int GREEN_DARK = 0xFF0AA84F;
    static final int TEXT = 0xFF151918;
    static final int MUTED = 0xFF737B78;
    static final int SOFT = 0xFFF1F4F1;
    static final int MAP = 0xFFE7EFE9;
    static final int RED = 0xFFFF5757;
    static final int RED_SOFT = 0xFFE36A6A;

    private UiKit() { }

    static int dp(Context context, float value) {
        return Math.round(value * context.getResources().getDisplayMetrics().density);
    }

    static GradientDrawable rounded(int color, float radiusDp, Context context) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(color);
        drawable.setCornerRadius(dp(context, radiusDp));
        return drawable;
    }

    static GradientDrawable bordered(int color, int stroke, float radiusDp, Context context) {
        GradientDrawable drawable = rounded(color, radiusDp, context);
        drawable.setStroke(dp(context, 1), stroke);
        return drawable;
    }

    static GradientDrawable hero(Context context) {
        GradientDrawable drawable = new GradientDrawable(
                GradientDrawable.Orientation.TL_BR,
                new int[]{0xFF8AB99C, 0xFF3E6E58, 0xFF173E31});
        drawable.setCornerRadii(new float[]{0, 0, 0, 0,
                dp(context, 30), dp(context, 30), dp(context, 30), dp(context, 30)});
        return drawable;
    }

    static Button button(Context context, String text, int background, int textColor) {
        Button button = new Button(context);
        button.setText(text);
        button.setTextColor(textColor);
        button.setTextSize(15);
        button.setAllCaps(false);
        button.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        button.setGravity(Gravity.CENTER);
        button.setBackground(rounded(background, 14, context));
        button.setMinHeight(dp(context, 52));
        button.setPadding(dp(context, 14), dp(context, 8), dp(context, 14), dp(context, 8));
        return button;
    }

    static TextView label(Context context, String text, float size, int color) {
        TextView view = new TextView(context);
        view.setText(text);
        view.setTextSize(size);
        view.setTextColor(color);
        return view;
    }

    static void hidden(View... views) {
        for (View view : views) view.setVisibility(View.GONE);
    }
}
