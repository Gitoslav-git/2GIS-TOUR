package ru.gulyay.app;

import android.app.Activity;
import android.os.Bundle;
import android.view.View;
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

    @Override public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        ScrollView scroll = new ScrollView(this);
        LinearLayout column = new LinearLayout(this);
        column.setOrientation(LinearLayout.VERTICAL);
        int padding = (int) (20 * getResources().getDisplayMetrics().density);
        column.setPadding(padding, padding, padding, padding);
        scroll.addView(column);

        TextView title = new TextView(this);
        title.setText("Гуляй · версия 0.1");
        title.setTextSize(27);
        column.addView(title);
        TextView intro = new TextView(this);
        intro.setText("Расскажите, как хотите провести прогулку. Первые города: Тула и Владимир.");
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
        } else {
            result.setText("Подключите backend по HTTPS. Версия 0.1 проверяет ввод и обработку ошибок; маршрут появится в следующем этапе.");
        }
        submit.setOnClickListener(view -> generate());
    }

    private void generate() {
        String text = query.getText().toString().trim();
        if (text.length() < 3 || text.length() > 1000) {
            query.setError("Введите от 3 до 1000 символов");
            return;
        }
        if (requestInFlight) return;
        requestInFlight = true;
        submit.setEnabled(false);
        result.setText("Проверяем запрос…");
        String cityId = city.getSelectedItemPosition() == 0 ? "tula" : "vladimir";
        String sessionId = getPreferences(MODE_PRIVATE).getString("deviceSessionId", null);
        if (sessionId == null) {
            sessionId = UUID.randomUUID().toString();
            getPreferences(MODE_PRIVATE).edit().putString("deviceSessionId", sessionId).apply();
        }
        final String owner = sessionId;
        network.execute(() -> {
            String message;
            try {
                message = ApiClient.createRoute(cityId, text, owner);
            } catch (Exception exception) {
                message = "Не удалось связаться с сервером. Проверьте интернет и адрес backend.";
            }
            String finalMessage = message;
            runOnUiThread(() -> {
                if (isFinishing() || isDestroyed()) return;
                result.setText(finalMessage);
                requestInFlight = false;
                submit.setEnabled(true);
            });
        });
    }

    @Override protected void onSaveInstanceState(Bundle out) {
        out.putInt("city", city.getSelectedItemPosition());
        out.putString("query", query.getText().toString());
        out.putString("result", result.getText().toString());
        super.onSaveInstanceState(out);
    }

    @Override protected void onDestroy() {
        network.shutdownNow();
        super.onDestroy();
    }
}
