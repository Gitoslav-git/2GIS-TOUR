package ru.gulyay.app;

import android.app.Activity;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.view.View;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Spinner;
import android.widget.TextView;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class MainActivity extends Activity {
    private final ExecutorService network = Executors.newSingleThreadExecutor();
    private Spinner city;
    private EditText query;
    private TextView result;
    private Button submit;
    private Button editPointsButton;
    private Button findPlaceButton;
    private Button addPlaceButton;
    private Button applyPointsButton;
    private LinearLayout pointEditor;
    private Spinner routePointSpinner;
    private Spinner foundPlaceSpinner;
    private EditText placeSearch;
    private TextView editorStatus;
    private TextView pendingPoints;
    private final List<ApiClient.PlaceOption> currentPoints = new ArrayList<>();
    private final List<ApiClient.PlaceOption> foundPlaces = new ArrayList<>();
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
        title.setText("Гуляй · версия 0.4.2");
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

        editPointsButton = new Button(this);
        editPointsButton.setText("Редактировать точки");
        editPointsButton.setEnabled(false);
        column.addView(editPointsButton);
        pointEditor = new LinearLayout(this);
        pointEditor.setOrientation(LinearLayout.VERTICAL);
        pointEditor.setVisibility(View.GONE);
        TextView editorTitle = new TextView(this);
        editorTitle.setText("Выберите точку: её можно удалить или передвинуть. Поиск добавляет только реальные места 2ГИС.");
        pointEditor.addView(editorTitle);
        routePointSpinner = new Spinner(this);
        pointEditor.addView(routePointSpinner);
        LinearLayout orderButtons = new LinearLayout(this);
        Button moveUp = new Button(this);
        moveUp.setText("Выше");
        Button moveDown = new Button(this);
        moveDown.setText("Ниже");
        Button remove = new Button(this);
        remove.setText("Удалить");
        orderButtons.addView(moveUp, new LinearLayout.LayoutParams(0, -2, 1));
        orderButtons.addView(moveDown, new LinearLayout.LayoutParams(0, -2, 1));
        orderButtons.addView(remove, new LinearLayout.LayoutParams(0, -2, 1));
        pointEditor.addView(orderButtons);
        placeSearch = new EditText(this);
        placeSearch.setHint("Найти место для добавления");
        placeSearch.setSingleLine(true);
        pointEditor.addView(placeSearch);
        findPlaceButton = new Button(this);
        findPlaceButton.setText("Найти в 2ГИС");
        pointEditor.addView(findPlaceButton);
        foundPlaceSpinner = new Spinner(this);
        pointEditor.addView(foundPlaceSpinner);
        addPlaceButton = new Button(this);
        addPlaceButton.setText("Добавить выбранное место");
        addPlaceButton.setEnabled(false);
        pointEditor.addView(addPlaceButton);
        pendingPoints = new TextView(this);
        pointEditor.addView(pendingPoints);
        applyPointsButton = new Button(this);
        applyPointsButton.setText("Применить изменения точек");
        pointEditor.addView(applyPointsButton);
        editorStatus = new TextView(this);
        pointEditor.addView(editorStatus);
        column.addView(pointEditor);
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
                result.setText("Версия 0.4.2 позволяет добавлять, удалять и переставлять точки маршрута.");
            }
        }
        editPointsButton.setEnabled(routeId != null);
        submit.setOnClickListener(view -> generate());
        editPointsButton.setOnClickListener(view -> loadPointEditor());
        moveUp.setOnClickListener(view -> moveSelectedPoint(-1));
        moveDown.setOnClickListener(view -> moveSelectedPoint(1));
        remove.setOnClickListener(view -> removeSelectedPoint());
        findPlaceButton.setOnClickListener(view -> searchPlaces());
        addPlaceButton.setOnClickListener(view -> addSelectedPlace());
        applyPointsButton.setOnClickListener(view -> applyPointChanges());
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
        setNetworkBusy(true);
        String cityId = city.getSelectedItemPosition() == 0 ? "tula" : "vladimir";
        boolean revise = routeId != null && cityId.equals(routeCityId);
        String previous = lastSuccessfulResult;
        result.setText(revise ? "Пересчитываем маршрут…" : "Разбираем пожелания и строим маршрут…");
        final String owner = sessionId();
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
                    editPointsButton.setEnabled(true);
                    currentPoints.clear();
                    currentPoints.addAll(finalResponse.points);
                    pointEditor.setVisibility(View.GONE);
                    persistRouteState(text);
                } else if (previous != null) {
                    result.setText(previous + "\n\nИзменение не применено: " + finalResponse.message);
                } else {
                    result.setText(finalResponse.message);
                }
                finishNetwork(finalResponse.retryAfterSeconds);
            });
        });
    }

    private String sessionId() {
        SharedPreferences preferences = getPreferences(MODE_PRIVATE);
        String value = preferences.getString("deviceSessionId", null);
        if (value == null) {
            value = UUID.randomUUID().toString();
            preferences.edit().putString("deviceSessionId", value).apply();
        }
        return value;
    }

    private void loadPointEditor() {
        if (requestInFlight || routeId == null) return;
        pointEditor.setVisibility(View.VISIBLE);
        editorStatus.setText("Загружаем актуальную версию маршрута…");
        setNetworkBusy(true);
        final String requestedRouteId = routeId;
        final String requestedCityId = routeCityId;
        final String currentQuery = query.getText().toString().trim();
        final String owner = sessionId();
        network.execute(() -> {
            ApiClient.Result response;
            try {
                response = ApiClient.getRoute(requestedRouteId, requestedCityId, owner);
                if (!response.success && "NOT_FOUND".equals(response.errorCode)) {
                    ApiClient.Result recreated = ApiClient.createRoute(
                            requestedCityId, currentQuery, owner);
                    if (recreated.success) {
                        response = new ApiClient.Result(true,
                                "Старый маршрут отсутствовал на сервере — построен новый.\n\n" +
                                        recreated.message,
                                recreated.routeId, recreated.routeVersion, 0, null,
                                recreated.points);
                    } else {
                        response = recreated;
                    }
                }
            } catch (Exception exception) {
                response = new ApiClient.Result(false,
                        "Не удалось загрузить маршрут с backend.", null, 0);
            }
            ApiClient.Result finalResponse = response;
            runOnUiThread(() -> {
                if (isFinishing() || isDestroyed()) return;
                if (finalResponse.success) {
                    routeId = finalResponse.routeId;
                    routeVersion = finalResponse.routeVersion;
                    currentPoints.clear();
                    currentPoints.addAll(finalResponse.points);
                    lastSuccessfulResult = finalResponse.message;
                    result.setText(finalResponse.message);
                    refreshPointEditor();
                    editorStatus.setText("Меняйте список, затем примените всё одной кнопкой.");
                    persistRouteState(currentQuery);
                } else {
                    editorStatus.setText(finalResponse.message);
                }
                finishNetwork(finalResponse.retryAfterSeconds);
            });
        });
    }

    private void searchPlaces() {
        String text = placeSearch.getText().toString().trim();
        if (text.length() < 2 || text.length() > 120) {
            placeSearch.setError("Введите от 2 до 120 символов");
            return;
        }
        if (requestInFlight || routeId == null) return;
        setNetworkBusy(true);
        editorStatus.setText("Ищем реальные места в 2ГИС…");
        final String requestedCityId = routeCityId;
        final String owner = sessionId();
        network.execute(() -> {
            ApiClient.SearchResult response;
            try {
                response = ApiClient.searchPlaces(requestedCityId, text, owner);
            } catch (Exception exception) {
                response = new ApiClient.SearchResult(false,
                        "Не удалось выполнить поиск мест.", 0, Collections.emptyList());
            }
            ApiClient.SearchResult finalResponse = response;
            runOnUiThread(() -> {
                if (isFinishing() || isDestroyed()) return;
                foundPlaces.clear();
                foundPlaces.addAll(finalResponse.items);
                foundPlaceSpinner.setAdapter(new ArrayAdapter<>(this,
                        android.R.layout.simple_spinner_dropdown_item, foundPlaces));
                addPlaceButton.setEnabled(finalResponse.success && !foundPlaces.isEmpty());
                editorStatus.setText(finalResponse.message);
                finishNetwork(finalResponse.retryAfterSeconds);
            });
        });
    }

    private void addSelectedPlace() {
        int position = foundPlaceSpinner.getSelectedItemPosition();
        if (position < 0 || position >= foundPlaces.size()) return;
        ApiClient.PlaceOption selected = foundPlaces.get(position);
        for (ApiClient.PlaceOption point : currentPoints) {
            if (point.placeId.equals(selected.placeId)) {
                editorStatus.setText("Эта точка уже есть в маршруте.");
                return;
            }
        }
        if (currentPoints.size() >= 8) {
            editorStatus.setText("В маршруте может быть не больше восьми точек.");
            return;
        }
        currentPoints.add(selected);
        refreshPointEditor();
        routePointSpinner.setSelection(currentPoints.size() - 1);
        editorStatus.setText("Точка добавлена в черновик. Нажмите «Применить изменения точек».");
    }

    private void removeSelectedPoint() {
        int position = routePointSpinner.getSelectedItemPosition();
        if (position < 0 || position >= currentPoints.size()) return;
        if (currentPoints.size() == 1) {
            editorStatus.setText("Нельзя удалить единственную точку маршрута.");
            return;
        }
        currentPoints.remove(position);
        refreshPointEditor();
        routePointSpinner.setSelection(Math.min(position, currentPoints.size() - 1));
        editorStatus.setText("Точка удалена из черновика. Изменения ещё не отправлены.");
    }

    private void moveSelectedPoint(int direction) {
        int position = routePointSpinner.getSelectedItemPosition();
        int target = position + direction;
        if (position < 0 || target < 0 || target >= currentPoints.size()) return;
        Collections.swap(currentPoints, position, target);
        refreshPointEditor();
        routePointSpinner.setSelection(target);
        editorStatus.setText("Порядок изменён в черновике. Изменения ещё не отправлены.");
    }

    private void refreshPointEditor() {
        routePointSpinner.setAdapter(new ArrayAdapter<>(this,
                android.R.layout.simple_spinner_dropdown_item, currentPoints));
        StringBuilder text = new StringBuilder("Новый порядок:");
        for (int i = 0; i < currentPoints.size(); i++) {
            text.append("\n").append(i + 1).append(". ").append(currentPoints.get(i));
        }
        pendingPoints.setText(text.toString());
        applyPointsButton.setEnabled(!currentPoints.isEmpty() && !requestInFlight);
    }

    private void applyPointChanges() {
        if (requestInFlight || routeId == null || currentPoints.isEmpty()) return;
        final List<ApiClient.PlaceOption> requestedPoints = new ArrayList<>(currentPoints);
        final String requestedRouteId = routeId;
        final int requestedVersion = routeVersion;
        final String requestedCityId = routeCityId;
        final String owner = sessionId();
        final String previous = lastSuccessfulResult;
        setNetworkBusy(true);
        editorStatus.setText("Проверяем точки и пересчитываем все переходы…");
        network.execute(() -> {
            ApiClient.Result response;
            boolean refreshedAfterConflict = false;
            try {
                response = ApiClient.revisePoints(requestedRouteId, requestedVersion,
                        requestedCityId, requestedPoints, owner);
                if (!response.success && "VERSION_CONFLICT".equals(response.errorCode)) {
                    ApiClient.Result latest = ApiClient.getRoute(requestedRouteId,
                            requestedCityId, owner);
                    if (latest.success) {
                        response = latest;
                        refreshedAfterConflict = true;
                    }
                }
            } catch (Exception exception) {
                response = new ApiClient.Result(false,
                        "Нет ответа от backend. Текущий маршрут не изменён.", null, 0);
            }
            ApiClient.Result finalResponse = response;
            boolean finalRefreshedAfterConflict = refreshedAfterConflict;
            runOnUiThread(() -> {
                if (isFinishing() || isDestroyed()) return;
                if (finalResponse.success) {
                    routeId = finalResponse.routeId;
                    routeVersion = finalResponse.routeVersion;
                    currentPoints.clear();
                    currentPoints.addAll(finalResponse.points);
                    lastSuccessfulResult = finalResponse.message;
                    result.setText(finalResponse.message);
                    refreshPointEditor();
                    editorStatus.setText(finalRefreshedAfterConflict
                            ? "Маршрут уже изменился. Загружена актуальная версия — повторите правки."
                            : "Точки применены, переходы и время пересчитаны.");
                    persistRouteState(query.getText().toString().trim());
                } else {
                    result.setText(previous + "\n\nИзменение точек не применено: " +
                            finalResponse.message);
                    editorStatus.setText("Исходный маршрут сохранён без изменений.");
                }
                finishNetwork(finalResponse.retryAfterSeconds);
            });
        });
    }

    private void setNetworkBusy(boolean busy) {
        requestInFlight = busy;
        submit.setEnabled(!busy);
        editPointsButton.setEnabled(!busy && routeId != null);
        findPlaceButton.setEnabled(!busy);
        addPlaceButton.setEnabled(!busy && !foundPlaces.isEmpty());
        applyPointsButton.setEnabled(!busy && !currentPoints.isEmpty());
    }

    private void finishNetwork(int retryAfterSeconds) {
        if (retryAfterSeconds > 0) {
            retryAllowedAtMillis = System.currentTimeMillis() + retryAfterSeconds * 1000L;
        }
        setNetworkBusy(false);
        applyCooldown();
    }

    private void applyCooldown() {
        long remaining = retryAllowedAtMillis - System.currentTimeMillis();
        if (remaining <= 0) {
            if (!requestInFlight) {
                submit.setEnabled(true);
                editPointsButton.setEnabled(routeId != null);
                findPlaceButton.setEnabled(true);
                addPlaceButton.setEnabled(!foundPlaces.isEmpty());
                applyPointsButton.setEnabled(!currentPoints.isEmpty());
            }
            return;
        }
        submit.setEnabled(false);
        editPointsButton.setEnabled(false);
        findPlaceButton.setEnabled(false);
        addPlaceButton.setEnabled(false);
        applyPointsButton.setEnabled(false);
        submit.postDelayed(() -> {
            if (!isFinishing() && !isDestroyed() && !requestInFlight) applyCooldown();
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
