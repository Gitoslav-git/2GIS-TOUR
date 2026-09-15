package ru.gulyay.app;

import android.app.Activity;
import android.os.Bundle;
import android.content.SharedPreferences;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Spinner;
import android.widget.TextView;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class MainActivity extends Activity {
    private final ExecutorService network = Executors.newSingleThreadExecutor();
    private Spinner city;
    private EditText query;
    private TextView result;
    private Button submit;
    private boolean requestInFlight;
    private String routeId;
    private int routeVersion;
    private String routeCityId;
    private String lastSuccessfulResult;
    private long retryAllowedAtMillis;

    @Override public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        ScrollView scroll = new ScrollView(this);
        LinearLayout column = new LinearLayout(this);
        column.setOrientation(LinearLayout.VERTICAL);
        int padding = (int) (20 * getResources().getDisplayMetrics().density);
        column.setPadding(padding, padding, padding, padding);
        scroll.addView(column);

        TextView title = new TextView(this);
        title.setText("Гуляй · версия 0.4.1");
        title.setTextSize(27);
        column.addView(title);
        TextView intro = new TextView(this);
        intro.setText("Расскажите, как хотите провести прогулку. Подберём реальные места и пешие переходы 2ГИС.");
        intro.setTextSize(17);
        column.addView(intro);
        city = new Spinner(this);
        city.setAdapter(new ArrayAdapter<>(this, android.R.layout.simple_spinner_dropdown_item,
                new String[]{"Тула", "Владимир"}));
        column.addView(city);
        query = new EditText(this);
        query.setHint("Например: хочу гулять 4 часа и зайти поесть");
        query.setMinLines(4);
        query.setGravity(android.view.Gravity.TOP);
        column.addView(query, new LinearLayout.LayoutParams(-1, -2));
        submit = new Button(this);
        submit.setText("Построить маршрут");
        column.addView(submit);
        result = new TextView(this);
        result.setTextSize(17);
        column.addView(result);
        setContentView(scroll);

        if (savedInstanceState != null) {
            city.setSelection(savedInstanceState.getInt("city"));
            query.setText(savedInstanceState.getString("query", ""));
            result.setText(savedInstanceState.getString("result", ""));
            routeId = savedInstanceState.getString("routeId");
            routeVersion = savedInstanceState.getInt("routeVersion", 0);
            routeCityId = savedInstanceState.getString("routeCityId");
            lastSuccessfulResult = savedInstanceState.getString("lastSuccessfulResult");
            retryAllowedAtMillis = savedInstanceState.getLong("retryAllowedAtMillis", 0);
            if (routeId != null) submit.setText("Изменить маршрут");
        } else {
            restoreRouteState();
            if (routeId == null) {
                result.setText("Версия 0.4.1 сохраняет маршруты после перезапуска и старается заполнить указанное время доступными местами.");
            }
        }
        submit.setOnClickListener(view -> generate());
        applyCooldown();
    }

    private void generate() {
        String text = query.getText().toString().trim();
        if (text.length() < 3 || text.length() > 1000) {
            query.setError("Введите от 3 до 1000 символов");
            return;
        }
        if (requestInFlight) return;
        if (System.currentTimeMillis() < retryAllowedAtMillis) {
            applyCooldown();
            return;
        }
        requestInFlight = true;
        submit.setEnabled(false);
        String cityId = city.getSelectedItemPosition() == 0 ? "tula" : "vladimir";
        boolean revise = routeId != null && cityId.equals(routeCityId);
        String previous = lastSuccessfulResult;
        result.setText(revise ? "Пересчитываем маршрут…" : "Разбираем пожелания и строим маршрут…");
        String sessionId = getPreferences(MODE_PRIVATE).getString("deviceSessionId", null);
        if (sessionId == null) {
            sessionId = UUID.randomUUID().toString();
            getPreferences(MODE_PRIVATE).edit().putString("deviceSessionId", sessionId).apply();
        }
        final String owner = sessionId;
        network.execute(() -> {
            ApiClient.Result response;
            try {
                response = revise
                        ? ApiClient.reviseRoute(routeId, routeVersion, cityId, text, owner)
                        : ApiClient.createRoute(cityId, text, owner);
            } catch (Exception exception) {
                response = new ApiClient.Result(false,
                        "Нет ответа от backend. Проверьте адрес сервера и доступность сети.", null, 0);
            }
            ApiClient.Result finalResponse = response;
            runOnUiThread(() -> {
                if (isFinishing() || isDestroyed()) return;
                if (finalResponse.success) {
                    retryAllowedAtMillis = 0;
                    routeId = finalResponse.routeId;
                    routeVersion = finalResponse.routeVersion;
                    routeCityId = cityId;
                    lastSuccessfulResult = finalResponse.message;
                    result.setText(finalResponse.message);
                    submit.setText("Изменить маршрут");
                    persistRouteState(text);
                } else if (previous != null) {
                    result.setText(previous + "\n\nИзменение не применено: " + finalResponse.message);
                } else {
                    result.setText(finalResponse.message);
                }
                if (finalResponse.retryAfterSeconds > 0) {
                    retryAllowedAtMillis = System.currentTimeMillis() + finalResponse.retryAfterSeconds * 1000L;
                }
                requestInFlight = false;
                applyCooldown();
            });
        });
    }

    private void applyCooldown() {
        long remaining = retryAllowedAtMillis - System.currentTimeMillis();
        if (remaining <= 0) {
            if (!requestInFlight) submit.setEnabled(true);
            return;
        }
        submit.setEnabled(false);
        submit.postDelayed(() -> {
            if (!isFinishing() && !isDestroyed() && !requestInFlight) submit.setEnabled(true);
        }, remaining + 100);
    }

    private void persistRouteState(String queryText) {
        getPreferences(MODE_PRIVATE).edit()
                .putString("routeId", routeId)
                .putInt("routeVersion", routeVersion)
                .putString("routeCityId", routeCityId)
                .putString("lastSuccessfulResult", lastSuccessfulResult)
                .putString("routeQuery", queryText)
                .apply();
    }

    private void restoreRouteState() {
        SharedPreferences preferences = getPreferences(MODE_PRIVATE);
        routeId = preferences.getString("routeId", null);
        routeVersion = preferences.getInt("routeVersion", 0);
        routeCityId = preferences.getString("routeCityId", null);
        lastSuccessfulResult = preferences.getString("lastSuccessfulResult", null);
        if (routeId == null || routeVersion < 1 || routeCityId == null || lastSuccessfulResult == null) {
            routeId = null;
            return;
        }
        city.setSelection("vladimir".equals(routeCityId) ? 1 : 0);
        query.setText(preferences.getString("routeQuery", ""));
        result.setText(lastSuccessfulResult);
        submit.setText("Изменить маршрут");
    }

    @Override protected void onSaveInstanceState(Bundle out) {
        out.putInt("city", city.getSelectedItemPosition());
        out.putString("query", query.getText().toString());
        out.putString("result", result.getText().toString());
        out.putString("routeId", routeId);
        out.putInt("routeVersion", routeVersion);
        out.putString("routeCityId", routeCityId);
        out.putString("lastSuccessfulResult", lastSuccessfulResult);
        out.putLong("retryAllowedAtMillis", retryAllowedAtMillis);
        super.onSaveInstanceState(out);
    }

    @Override protected void onDestroy() {
        network.shutdownNow();
        super.onDestroy();
    }
}
