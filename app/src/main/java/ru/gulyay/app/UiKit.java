package ru.gulyay.app;

import android.content.Context;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.TextView;

final class UiKit {
    static final int GREEN = 0xFF16A34A;
    static final int GREEN_DARK = 0xFF0E5A3C;
    static final int MINT = 0xFFA7E3BC;
    static final int TEXT = 0xFF1F2937;
    static final int MUTED = 0xFF6B7280;
    static final int SOFT = 0xFFF1FBF5;
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
                new int[]{0xFFF1FBF5, 0xFFDDF3E5, 0xFFFFFFFF});
        return drawable;
    }

    static GradientDrawable gradient(int[] colors, float radiusDp, Context context) {
        GradientDrawable drawable = new GradientDrawable(
                GradientDrawable.Orientation.LEFT_RIGHT, colors);
        drawable.setCornerRadius(dp(context, radiusDp));
        return drawable;
    }

    static GradientDrawable verticalGradient(int[] colors, float radiusDp, Context context) {
        GradientDrawable drawable = new GradientDrawable(
                GradientDrawable.Orientation.TOP_BOTTOM, colors);
        drawable.setCornerRadius(dp(context, radiusDp));
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
