package ru.gulyay.app;

import android.Manifest;
import android.app.Activity;
import android.content.SharedPreferences;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.location.Location;
import android.location.LocationListener;
import android.location.LocationManager;
import android.os.Bundle;
import android.os.Looper;
import android.view.View;
import android.widget.ArrayAdapter;
import android.widget.AdapterView;
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
    private static final int LOCATION_PERMISSION_REQUEST = 75;
    private final ExecutorService network = Executors.newSingleThreadExecutor();
    private Spinner city;
    private EditText query;
    private TextView result;
    private Button submit;
    private Button editPointsButton;
    private Button findPlaceButton;
    private Button addPlaceButton;
    private Button applyPointsButton;
    private Button mapButton;
    private Button locationButton;
    private LinearLayout pointEditor;
    private Spinner routePointSpinner;
    private Spinner foundPlaceSpinner;
    private EditText placeSearch;
    private TextView editorStatus;
    private TextView pendingPoints;
    private TextView locationStatus;
    private final List<ApiClient.PlaceOption> currentPoints = new ArrayList<>();
    private final List<ApiClient.PlaceOption> foundPlaces = new ArrayList<>();
    private boolean requestInFlight;
    private String routeId;
    private int routeVersion;
    private String routeCityId;
    private String lastSuccessfulResult;
    private long retryAllowedAtMillis;
    private Double startLat;
    private Double startLon;
    private Double startAccuracyMeters;
    private boolean routeLocationDirty;
    private LocationManager locationManager;
    private LocationListener locationListener;
    private boolean locationResolved;

    @Override public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        ScrollView scroll = new ScrollView(this);
        LinearLayout column = new LinearLayout(this);
        column.setOrientation(LinearLayout.VERTICAL);
        int padding = (int) (20 * getResources().getDisplayMetrics().density);
        column.setPadding(padding, padding, padding, padding);
        scroll.addView(column);

        TextView title = new TextView(this);
        title.setText("Гуляй · версия 0.5.3");
        title.setTextSize(27);
        column.addView(title);
        TextView intro = new TextView(this);
        intro.setText("Расскажите, как хотите провести прогулку. Подберём реальные места и пешие переходы 2ГИС.");
        intro.setTextSize(17);
        column.addView(intro);
        city = new Spinner(this);
        city.setAdapter(new ArrayAdapter<>(this, android.R.layout.simple_spinner_dropdown_item,
                new String[]{"Локация не определена", "Тула", "Владимир", "Москва"}));
        column.addView(city);
        locationButton = new Button(this);
        locationButton.setText("Обновить геопозицию");
        column.addView(locationButton);
        locationStatus = new TextView(this);
        locationStatus.setText("Определяем город. Если не получится — выберите его в списке.");
        column.addView(locationStatus);
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
        mapButton = new Button(this);
        mapButton.setText("Показать на карте 2ГИС");
        mapButton.setEnabled(false);
        column.addView(mapButton);
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
            if (savedInstanceState.containsKey("startLat")) {
                startLat = savedInstanceState.getDouble("startLat");
                startLon = savedInstanceState.getDouble("startLon");
                startAccuracyMeters = savedInstanceState.getDouble("startAccuracyMeters", 100.0);
                String restoredCityId = cityIdForLocation(startLat, startLon);
                if (restoredCityId != null) {
                    city.setSelection(cityPosition(restoredCityId));
                    showLocation(restoredCityId);
                } else {
                    clearLocationToUnknown();
                }
            }
            routeLocationDirty = savedInstanceState.getBoolean("routeLocationDirty", false);
            if (routeId != null) submit.setText("Изменить маршрут");
        } else {
            restoreRouteState();
            if (routeId == null) {
                result.setText("Версия 0.5.3 различает старт, направление и область прогулки.");
            }
        }
        editPointsButton.setEnabled(routeId != null);
        mapButton.setEnabled(routeId != null);
        submit.setOnClickListener(view -> generate());
        locationButton.setOnClickListener(view -> toggleLocation());
        city.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
            @Override public void onItemSelected(AdapterView<?> parent, View view,
                                                  int position, long id) {
                String selected = selectedCityId();
                if (selected != null && startLat != null && startLon != null
                        && !locationMatchesCity(selected, startLat, startLon)) {
                    clearCoordinatesKeepingCity();
                    locationStatus.setText("Город выбран вручную. Маршрут будет рассчитан от его области.");
                }
            }
            @Override public void onNothingSelected(AdapterView<?> parent) { }
        });
        mapButton.setOnClickListener(view -> openMap());
        editPointsButton.setOnClickListener(view -> loadPointEditor());
        moveUp.setOnClickListener(view -> moveSelectedPoint(-1));
        moveDown.setOnClickListener(view -> moveSelectedPoint(1));
        remove.setOnClickListener(view -> removeSelectedPoint());
        findPlaceButton.setOnClickListener(view -> searchPlaces());
        addPlaceButton.setOnClickListener(view -> addSelectedPlace());
        applyPointsButton.setOnClickListener(view -> applyPointChanges());
        applyCooldown();
        showLocationRebuildIfNeeded();
        beginAutomaticLocationDetection();
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
        String cityId = selectedCityId();
        if (cityId == null) {
            setNetworkBusy(false);
            locationStatus.setText("Локация не определена. Выберите Тулу, Владимир или Москву в списке.");
            return;
        }
        if (startLat != null && startLon != null && !locationMatchesCity(cityId, startLat, startLon)) {
            clearCoordinatesKeepingCity();
            locationStatus.setText("Город выбран вручную. Старт рассчитан от выбранной области города.");
        }
        boolean revise = routeId != null && cityId.equals(routeCityId) && !routeLocationDirty;
        String previous = lastSuccessfulResult;
        result.setText(revise ? "Пересчитываем маршрут…" : "Разбираем пожелания и строим маршрут…");
        final String owner = sessionId();
        network.execute(() -> {
            ApiClient.Result response;
            try {
                response = revise
                        ? ApiClient.reviseRoute(routeId, routeVersion, cityId, text, owner,
                                startLat, startLon, startAccuracyMeters)
                        : ApiClient.createRoute(cityId, text, owner, startLat, startLon,
                                startAccuracyMeters);
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
                    routeLocationDirty = false;
                    lastSuccessfulResult = finalResponse.message;
                    result.setText(finalResponse.message);
                    submit.setText("Изменить маршрут");
                    editPointsButton.setEnabled(true);
                    mapButton.setEnabled(true);
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
                            requestedCityId, currentQuery, owner, startLat, startLon,
                            startAccuracyMeters);
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
        mapButton.setEnabled(!busy && routeId != null);
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
                mapButton.setEnabled(routeId != null);
                findPlaceButton.setEnabled(true);
                addPlaceButton.setEnabled(!foundPlaces.isEmpty());
                applyPointsButton.setEnabled(!currentPoints.isEmpty());
            }
            return;
        }
        submit.setEnabled(false);
        editPointsButton.setEnabled(false);
        mapButton.setEnabled(false);
        findPlaceButton.setEnabled(false);
        addPlaceButton.setEnabled(false);
        applyPointsButton.setEnabled(false);
        submit.postDelayed(() -> {
            if (!isFinishing() && !isDestroyed() && !requestInFlight) applyCooldown();
        }, remaining + 100);
    }

    private void persistRouteState(String queryText) {
        SharedPreferences.Editor editor = getPreferences(MODE_PRIVATE).edit()
                .putString("routeId", routeId)
                .putInt("routeVersion", routeVersion)
                .putString("routeCityId", routeCityId)
                .putString("lastSuccessfulResult", lastSuccessfulResult)
                .putString("routeQuery", queryText);
        editor.remove("startLatBits").remove("startLonBits").remove("startAccuracyBits");
        editor.putBoolean("routeLocationDirty", routeLocationDirty)
                .remove("routeStartLatBits").remove("routeStartLonBits");
        editor.apply();
    }

    private void restoreRouteState() {
        SharedPreferences preferences = getPreferences(MODE_PRIVATE);
        routeId = preferences.getString("routeId", null);
        routeVersion = preferences.getInt("routeVersion", 0);
        routeCityId = preferences.getString("routeCityId", null);
        lastSuccessfulResult = preferences.getString("lastSuccessfulResult", null);
        preferences.edit().remove("startLatBits").remove("startLonBits")
                .remove("startAccuracyBits").apply();
        routeLocationDirty = preferences.getBoolean("routeLocationDirty", false);
        if (routeId == null || routeVersion < 1 || routeCityId == null || lastSuccessfulResult == null) {
            routeId = null;
            return;
        }
        city.setSelection(0);
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
        if (startLat != null && startLon != null) {
            out.putDouble("startLat", startLat);
            out.putDouble("startLon", startLon);
            out.putDouble("startAccuracyMeters",
                    startAccuracyMeters == null ? 100.0 : startAccuracyMeters);
        }
        out.putBoolean("routeLocationDirty", routeLocationDirty);
        super.onSaveInstanceState(out);
    }

    private void toggleLocation() {
        if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) !=
                PackageManager.PERMISSION_GRANTED &&
                checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) !=
                        PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.ACCESS_FINE_LOCATION,
                    Manifest.permission.ACCESS_COARSE_LOCATION}, LOCATION_PERMISSION_REQUEST);
            return;
        }
        requestCurrentLocation();
    }

    private void beginAutomaticLocationDetection() {
        if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) ==
                PackageManager.PERMISSION_GRANTED ||
                checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) ==
                        PackageManager.PERMISSION_GRANTED) {
            requestCurrentLocation();
        } else {
            city.setSelection(0);
            requestPermissions(new String[]{Manifest.permission.ACCESS_FINE_LOCATION,
                    Manifest.permission.ACCESS_COARSE_LOCATION}, LOCATION_PERMISSION_REQUEST);
        }
    }

    @Override public void onRequestPermissionsResult(int requestCode, String[] permissions,
                                                     int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode != LOCATION_PERMISSION_REQUEST) return;
        boolean granted = false;
        for (int result : grantResults) granted |= result == PackageManager.PERMISSION_GRANTED;
        if (granted) requestCurrentLocation();
        else {
            city.setSelection(0);
            locationStatus.setText("Локация не определена. Выберите доступный город вручную.");
        }
    }

    private void requestCurrentLocation() {
        locationManager = (LocationManager) getSystemService(LOCATION_SERVICE);
        boolean gpsEnabled = locationManager.isProviderEnabled(LocationManager.GPS_PROVIDER);
        boolean networkEnabled = locationManager.isProviderEnabled(LocationManager.NETWORK_PROVIDER);
        if (!gpsEnabled && !networkEnabled) {
            clearLocationToUnknown();
            locationStatus.setText("Геопозиция выключена. Включите её или выберите город вручную.");
            return;
        }
        locationResolved = false;
        locationButton.setEnabled(false);
        locationStatus.setText("Определяем город и уточняем текущую позицию…");
        if (locationListener != null) {
            try { locationManager.removeUpdates(locationListener); } catch (SecurityException ignored) { }
            locationListener = null;
        }
        Location cached = bestLastKnownLocation(gpsEnabled, networkEnabled);
        if (cached != null) {
            String cachedCity = cityIdForLocation(cached.getLatitude(), cached.getLongitude());
            if (cachedCity != null) {
                city.setSelection(cityPosition(cachedCity));
                locationStatus.setText("Определён город: " + cityName(cachedCity) +
                        ". Уточняем свежие координаты…");
            }
        }
        locationListener = new LocationListener() {
            @Override public void onLocationChanged(Location location) {
                acceptLocation(location);
            }
            @Override public void onProviderDisabled(String providerName) { }
            @Override public void onProviderEnabled(String providerName) { }
            @Override public void onStatusChanged(String providerName, int status, Bundle extras) { }
        };
        try {
            if (gpsEnabled) {
                locationManager.requestSingleUpdate(LocationManager.GPS_PROVIDER,
                        locationListener, Looper.getMainLooper());
            }
            if (networkEnabled) {
                locationManager.requestSingleUpdate(LocationManager.NETWORK_PROVIDER,
                        locationListener, Looper.getMainLooper());
            }
            locationButton.postDelayed(() -> {
                if (locationListener == null) return;
                locationManager.removeUpdates(locationListener);
                locationListener = null;
                locationButton.setEnabled(true);
                if (!locationResolved && selectedCityId() == null) {
                    locationStatus.setText("Локация не определена. Выберите доступный город вручную.");
                } else if (!locationResolved) {
                    locationStatus.setText("Город определён по последней позиции. " +
                            "Точные координаты не получены — старт будет от области города.");
                }
            }, 20_000L);
        } catch (SecurityException error) {
            locationButton.setEnabled(true);
            clearLocationToUnknown();
            locationStatus.setText("Нет разрешения на геопозицию. Выберите город вручную.");
        }
    }

    private Location bestLastKnownLocation(boolean gpsEnabled, boolean networkEnabled) {
        Location best = null;
        try {
            if (gpsEnabled) best = locationManager.getLastKnownLocation(LocationManager.GPS_PROVIDER);
            if (networkEnabled) {
                Location networkLocation = locationManager.getLastKnownLocation(
                        LocationManager.NETWORK_PROVIDER);
                if (networkLocation != null && (best == null
                        || networkLocation.getTime() > best.getTime())) best = networkLocation;
            }
            Location passiveLocation = locationManager.getLastKnownLocation(
                    LocationManager.PASSIVE_PROVIDER);
            if (passiveLocation != null && (best == null
                    || passiveLocation.getTime() > best.getTime())) best = passiveLocation;
        } catch (SecurityException ignored) { }
        return best;
    }

    private void acceptLocation(Location location) {
        String cityId = cityIdForLocation(location.getLatitude(), location.getLongitude());
        if (cityId == null) {
            startLat = null;
            startLon = null;
            startAccuracyMeters = null;
            city.setSelection(0);
            locationStatus.setText("Получены координаты вне доступных городов. " +
                    "Ожидаем другой источник геопозиции…");
            return;
        }
        if (locationManager != null && locationListener != null) {
            locationManager.removeUpdates(locationListener);
            locationListener = null;
        }
        locationResolved = true;
        startLat = location.getLatitude();
        startLon = location.getLongitude();
        startAccuracyMeters = location.hasAccuracy() ? (double) location.getAccuracy() : 100.0;
        city.setSelection(cityPosition(cityId));
        locationButton.setEnabled(true);
        showLocation(cityId);
        markRouteLocationDirty();
    }

    private void showLocation(String cityId) {
        locationButton.setText("Обновить геопозицию");
        locationStatus.setText(String.format(java.util.Locale.US,
                "Определён город: %s. Геопозиция получена (точность ±%.0f м).",
                cityName(cityId), startAccuracyMeters == null ? 100.0 : startAccuracyMeters));
    }

    private void clearCoordinatesKeepingCity() {
        startLat = null;
        startLon = null;
        startAccuracyMeters = null;
        locationButton.setText("Обновить геопозицию");
        markRouteLocationDirty();
    }

    private void clearLocationToUnknown() {
        clearCoordinatesKeepingCity();
        city.setSelection(0);
    }

    private String selectedCityId() {
        int position = city.getSelectedItemPosition();
        return position == 3 ? "moscow" : (position == 2 ? "vladimir" :
                (position == 1 ? "tula" : null));
    }

    private static int cityPosition(String cityId) {
        return "moscow".equals(cityId) ? 3 : ("vladimir".equals(cityId) ? 2 : 1);
    }

    private static String cityName(String cityId) {
        return "moscow".equals(cityId) ? "Москва" :
                ("vladimir".equals(cityId) ? "Владимир" : "Тула");
    }

    private static String cityIdForLocation(double lat, double lon) {
        if (locationMatchesCity("moscow", lat, lon)) return "moscow";
        if (locationMatchesCity("vladimir", lat, lon)) return "vladimir";
        if (locationMatchesCity("tula", lat, lon)) return "tula";
        return null;
    }

    private static boolean locationMatchesCity(String cityId, double lat, double lon) {
        double centerLat = 54.1930, centerLon = 37.6178, limitKm = 50.0;
        if ("vladimir".equals(cityId)) { centerLat = 56.1291; centerLon = 40.4075; }
        if ("moscow".equals(cityId)) { centerLat = 55.7558; centerLon = 37.6173; limitKm = 80.0; }
        double latKm = (lat - centerLat) * 111.32;
        double lonKm = (lon - centerLon) * 111.32 * Math.cos(Math.toRadians(centerLat));
        return Math.sqrt(latKm * latKm + lonKm * lonKm) <= limitKm;
    }

    private void markRouteLocationDirty() {
        if (routeId == null) return;
        routeLocationDirty = true;
        getPreferences(MODE_PRIVATE).edit().putBoolean("routeLocationDirty", true).apply();
        showLocationRebuildIfNeeded();
    }

    private void showLocationRebuildIfNeeded() {
        if (routeId == null || !routeLocationDirty) return;
        submit.setText("Перестроить от новой позиции");
        locationStatus.append(" Перестройте маршрут, чтобы учесть новый старт.");
    }

    private void openMap() {
        if (routeId == null || routeCityId == null) return;
        Intent intent = new Intent(this, MapActivity.class);
        intent.putExtra(MapActivity.EXTRA_ROUTE_ID, routeId);
        intent.putExtra(MapActivity.EXTRA_CITY_ID, routeCityId);
        intent.putExtra(MapActivity.EXTRA_SESSION_ID, sessionId());
        if (startLat != null && startLon != null) {
            intent.putExtra(MapActivity.EXTRA_USER_LAT, startLat);
            intent.putExtra(MapActivity.EXTRA_USER_LON, startLon);
        }
        startActivity(intent);
    }

    @Override protected void onDestroy() {
        if (locationManager != null && locationListener != null) {
            locationManager.removeUpdates(locationListener);
            locationListener = null;
        }
        network.shutdownNow();
        super.onDestroy();
    }
}
