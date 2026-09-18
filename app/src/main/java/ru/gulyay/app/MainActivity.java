package ru.gulyay.app;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.SharedPreferences;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.location.Location;
import android.location.LocationListener;
import android.location.LocationManager;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.graphics.Typeface;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowManager;
import android.view.inputmethod.InputMethodManager;
import android.widget.ArrayAdapter;
import android.widget.AdapterView;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.HorizontalScrollView;
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
    private static final int ROUTE_SCREEN_REQUEST = 76;
    private static final long GEO_ATTEMPT_WINDOW_MILLIS = 60_000L;
    private final ExecutorService network = Executors.newSingleThreadExecutor();
    private final Handler uiHandler = new Handler(Looper.getMainLooper());
    private Spinner city;
    private TextView cityArrow;
    private EditText query;
    private TextView result;
    private Button submit;
    private Button returnToRouteButton;
    private Button editPointsButton;
    private Button findPlaceButton;
    private Button addPlaceButton;
    private Button applyPointsButton;
    private Button mapButton;
    private Button startWalkButton;
    private Button resetRouteButton;
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
    private Runnable locationTimeout;
    private boolean locationResolved;
    private boolean queryEditMode;

    @Override public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_NOTHING);
        LinearLayout column = new LinearLayout(this);
        column.setOrientation(LinearLayout.VERTICAL);
        column.setBackgroundColor(0xFFFAFBFA);

        int p = UiKit.dp(this, 20);
        int screenHeightDp = getResources().getConfiguration().screenHeightDp;
        boolean compact = screenHeightDp <= 720;
        boolean veryCompact = screenHeightDp <= 640;
        FrameLayout hero = new FrameLayout(this);
        hero.setBackground(UiKit.hero(this));
        column.addView(hero, new LinearLayout.LayoutParams(
                -1, UiKit.dp(this, veryCompact ? 150 : (compact ? 170 : 205))));
        TextView brand = UiKit.label(this, "● Гуляй", compact ? 27 : 30, 0xFFFFFFFF);
        brand.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        FrameLayout.LayoutParams brandParams = new FrameLayout.LayoutParams(-2, -2);
        brandParams.leftMargin = p;
        brandParams.topMargin = UiKit.dp(this, compact ? 16 : 24);
        hero.addView(brand, brandParams);
        TextView subtitle = UiKit.label(this, "Маршрут под настроение", 15, 0xE6FFFFFF);
        FrameLayout.LayoutParams subtitleParams = new FrameLayout.LayoutParams(-2, -2);
        subtitleParams.leftMargin = p;
        subtitleParams.topMargin = UiKit.dp(this, compact ? 54 : 66);
        hero.addView(subtitle, subtitleParams);
        Button profile = UiKit.button(this, "☺", 0xE6FFFFFF, UiKit.TEXT);
        profile.setTextSize(22);
        profile.setMinWidth(UiKit.dp(this, 52));
        FrameLayout.LayoutParams profileParams = new FrameLayout.LayoutParams(
                UiKit.dp(this, 52), UiKit.dp(this, 52), Gravity.TOP | Gravity.END);
        profileParams.topMargin = UiKit.dp(this, compact ? 13 : 20);
        profileParams.rightMargin = p;
        hero.addView(profile, profileParams);

        FrameLayout cityPicker = new FrameLayout(this);
        cityPicker.setBackground(UiKit.rounded(0xEFFFFFFF, 18, this));
        city = new Spinner(this);
        city.setAdapter(new ArrayAdapter<>(this, android.R.layout.simple_spinner_dropdown_item,
                new String[]{"Локация не определена", "Тула", "Владимир", "Москва",
                        "Боровск, Калужская область"}));
        city.setPadding(UiKit.dp(this, 16), 0, UiKit.dp(this, 48), 0);
        city.setBackgroundColor(0x00000000);
        cityPicker.addView(city, new FrameLayout.LayoutParams(-1, -1));
        cityArrow = UiKit.label(this, "▼", 18, UiKit.RED_SOFT);
        cityArrow.setGravity(Gravity.CENTER);
        cityArrow.setClickable(true);
        cityArrow.setOnClickListener(view -> city.performClick());
        FrameLayout.LayoutParams arrowParams = new FrameLayout.LayoutParams(
                UiKit.dp(this, 48), -1, Gravity.END | Gravity.CENTER_VERTICAL);
        cityPicker.addView(cityArrow, arrowParams);
        FrameLayout.LayoutParams cityParams = new FrameLayout.LayoutParams(
                -1, UiKit.dp(this, compact ? 48 : 54), Gravity.BOTTOM);
        cityParams.setMargins(p, 0, p, UiKit.dp(this, compact ? 14 : 20));
        hero.addView(cityPicker, cityParams);

        LinearLayout content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(p, UiKit.dp(this, compact ? 10 : 16), p,
                UiKit.dp(this, compact ? 5 : 9));
        column.addView(content, new LinearLayout.LayoutParams(-1, 0, 1));
        TextView heading = UiKit.label(this, "Куда пойдём?", compact ? 22 : 25, UiKit.TEXT);
        heading.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        content.addView(heading);
        TextView intro = UiKit.label(this,
                "Расскажите, как хотите провести прогулку", 15, UiKit.MUTED);
        intro.setPadding(0, UiKit.dp(this, 1), 0, UiKit.dp(this, compact ? 5 : 8));
        content.addView(intro);

        locationButton = new Button(this);
        locationButton.setText("Обновить геопозицию");
        locationStatus = new TextView(this);
        locationStatus.setText("Определяем город. Если не получится — выберите его в списке.");
        locationStatus.setTextColor(UiKit.MUTED);
        locationStatus.setTextSize(compact ? 11 : 12);
        locationStatus.setMaxLines(compact ? 1 : 2);
        locationStatus.setEllipsize(android.text.TextUtils.TruncateAt.END);
        content.addView(locationStatus);
        locationButton.setVisibility(View.GONE);

        query = new EditText(this);
        query.setHint("Например: хочу гулять 2 часа по центру и зайти поесть");
        query.setMinLines(compact ? 2 : 3);
        query.setMaxLines(compact ? 2 : 3);
        query.setTextSize(compact ? 14 : 16);
        query.setGravity(Gravity.TOP);
        query.setPadding(UiKit.dp(this, 16), UiKit.dp(this, 14), UiKit.dp(this, 16), UiKit.dp(this, 14));
        query.setBackground(UiKit.bordered(0xFFFFFFFF, 0xFFE0E5E1, 16, this));
        LinearLayout.LayoutParams queryParams = new LinearLayout.LayoutParams(
                -1, UiKit.dp(this, veryCompact ? 58 : (compact ? 64 : 82)));
        queryParams.topMargin = UiKit.dp(this, compact ? 5 : 8);
        content.addView(query, queryParams);

        TextView filtersTitle = UiKit.label(this, "Быстрые фильтры", 14, UiKit.MUTED);
        filtersTitle.setPadding(0, UiKit.dp(this, compact ? 6 : 9), 0,
                UiKit.dp(this, compact ? 3 : 5));
        content.addView(filtersTitle);
        FrameLayout filtersViewport = new FrameLayout(this);
        filtersViewport.setBackgroundColor(0xFFFAFBFA);
        filtersViewport.setClipChildren(true);
        filtersViewport.setClipToPadding(true);
        HorizontalScrollView filtersScroll = new HorizontalScrollView(this);
        filtersScroll.setHorizontalScrollBarEnabled(false);
        filtersScroll.setOverScrollMode(View.OVER_SCROLL_NEVER);
        filtersScroll.setClipChildren(true);
        filtersScroll.setClipToPadding(true);
        filtersScroll.setPadding(0, UiKit.dp(this, 2), UiKit.dp(this, 12), UiKit.dp(this, 2));
        LinearLayout filters = new LinearLayout(this);
        filters.setOrientation(LinearLayout.HORIZONTAL);
        filters.setPadding(0, 0, UiKit.dp(this, 4), 0);
        filtersScroll.addView(filters);
        addFilterStub(filters, "2 часа");
        addFilterStub(filters, "С детьми");
        addFilterStub(filters, "Поесть");
        addFilterStub(filters, "Необычное");
        addFilterStub(filters, "Без музеев");
        addFilterStub(filters, "Мало ходить");
        filtersViewport.addView(filtersScroll, new FrameLayout.LayoutParams(-1, -1));
        content.addView(filtersViewport, new LinearLayout.LayoutParams(
                -1, UiKit.dp(this, compact ? 42 : 46)));

        submit = UiKit.button(this, "Построить маршрут", UiKit.GREEN, 0xFFFFFFFF);
        submit.setTextSize(compact ? 13 : 14);
        submit.setSingleLine(true);
        submit.setMinWidth(0);
        submit.setMinHeight(0);
        submit.setElevation(0f);
        submit.setStateListAnimator(null);
        submit.setPadding(UiKit.dp(this, 5), 0, UiKit.dp(this, 5), 0);
        returnToRouteButton = UiKit.button(this, "Вернуться к маршруту", UiKit.SOFT,
                UiKit.GREEN_DARK);
        returnToRouteButton.setTextSize(compact ? 12 : 13);
        returnToRouteButton.setSingleLine(true);
        returnToRouteButton.setMinWidth(0);
        returnToRouteButton.setMinHeight(0);
        returnToRouteButton.setElevation(0f);
        returnToRouteButton.setStateListAnimator(null);
        returnToRouteButton.setPadding(UiKit.dp(this, 4), 0, UiKit.dp(this, 4), 0);
        returnToRouteButton.setVisibility(View.GONE);
        LinearLayout routeActions = new LinearLayout(this);
        routeActions.setOrientation(LinearLayout.HORIZONTAL);
        routeActions.setGravity(Gravity.CENTER_VERTICAL);
        routeActions.setBaselineAligned(false);
        routeActions.setClipChildren(true);
        routeActions.setClipToPadding(true);
        LinearLayout.LayoutParams submitParams = new LinearLayout.LayoutParams(
                0, UiKit.dp(this, compact ? 48 : 54), 1f);
        routeActions.addView(submit, submitParams);
        LinearLayout.LayoutParams returnParams = new LinearLayout.LayoutParams(
                0, UiKit.dp(this, compact ? 48 : 54), 1.18f);
        returnParams.leftMargin = UiKit.dp(this, 6);
        routeActions.addView(returnToRouteButton, returnParams);
        LinearLayout.LayoutParams actionsParams = new LinearLayout.LayoutParams(
                -1, UiKit.dp(this, compact ? 48 : 54));
        actionsParams.topMargin = UiKit.dp(this, compact ? 4 : 8);
        actionsParams.bottomMargin = UiKit.dp(this, 4);
        content.addView(routeActions, actionsParams);
        result = new TextView(this);
        result.setTextSize(14);
        result.setTextColor(UiKit.MUTED);
        result.setMaxLines(1);
        result.setEllipsize(android.text.TextUtils.TruncateAt.END);
        result.setPadding(0, UiKit.dp(this, compact ? 3 : 6), 0,
                UiKit.dp(this, compact ? 3 : 6));
        content.addView(result, new LinearLayout.LayoutParams(-1,
                UiKit.dp(this, compact ? 22 : 28)));

        TextView historyTitle = UiKit.label(this, "История маршрутов",
                compact ? 17 : 20, UiKit.TEXT);
        historyTitle.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        content.addView(historyTitle);
        TextView history = UiKit.label(this,
                "🔒  История появится после входа в профиль", 15, UiKit.MUTED);
        history.setGravity(Gravity.CENTER);
        history.setBackground(UiKit.rounded(UiKit.SOFT, 16, this));
        LinearLayout.LayoutParams historyParams = new LinearLayout.LayoutParams(-1, UiKit.dp(this, 86));
        historyParams.height = UiKit.dp(this, compact ? 52 : 68);
        historyParams.topMargin = UiKit.dp(this, compact ? 4 : 7);
        content.addView(history, historyParams);

        editPointsButton = new Button(this);
        editPointsButton.setText("Редактировать точки");
        editPointsButton.setEnabled(false);
        content.addView(editPointsButton);
        startWalkButton = new Button(this);
        startWalkButton.setText("Начать прогулку");
        startWalkButton.setEnabled(false);
        startWalkButton.setVisibility(View.GONE);
        content.addView(startWalkButton);
        mapButton = new Button(this);
        mapButton.setText("Показать на карте 2ГИС");
        mapButton.setEnabled(false);
        content.addView(mapButton);
        resetRouteButton = new Button(this);
        resetRouteButton.setText("Сбросить маршрут");
        resetRouteButton.setVisibility(View.GONE);
        content.addView(resetRouteButton);
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
        content.addView(pointEditor);
        UiKit.hidden(editPointsButton, startWalkButton, mapButton, resetRouteButton);

        LinearLayout navigation = new LinearLayout(this);
        navigation.setGravity(Gravity.CENTER);
        navigation.setPadding(p, UiKit.dp(this, 2), p, UiKit.dp(this, 2));
        navigation.setBackground(UiKit.bordered(0xFFFFFFFF, 0xFFE6EAE7, 0, this));
        Button homeTab = navigationTab("⌂\nГлавная", UiKit.GREEN_DARK);
        Button profileTab = navigationTab("♙\nПрофиль", UiKit.MUTED);
        int navigationHeight = UiKit.dp(this, veryCompact ? 48 : 54);
        navigation.addView(homeTab, new LinearLayout.LayoutParams(0, navigationHeight, 1));
        navigation.addView(profileTab, new LinearLayout.LayoutParams(0, navigationHeight, 1));
        column.addView(navigation);
        setContentView(column);

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
            queryEditMode = savedInstanceState.getBoolean("queryEditMode", false);
            if (routeId != null) submit.setText("Изменить маршрут");
        } else {
            restoreRouteState();
            if (routeId == null) {
                result.setText("Версия 0.6 поддерживает ограничение пеших переходов и прохождение маршрута.");
            }
        }
        editPointsButton.setEnabled(routeId != null);
        startWalkButton.setEnabled(routeId != null);
        mapButton.setEnabled(routeId != null);
        submit.setOnClickListener(view -> generate());
        returnToRouteButton.setOnClickListener(view -> returnToCurrentRoute());
        locationButton.setOnClickListener(view -> toggleLocation());
        city.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
            @Override public void onItemSelected(AdapterView<?> parent, View view,
                                                  int position, long id) {
                updateCityArrow();
                String selected = selectedCityId();
                if (selected != null && startLat != null && startLon != null
                        && !locationMatchesCity(selected, startLat, startLon)) {
                    clearCoordinatesKeepingCity();
                    locationStatus.setText("Город выбран вручную. Если в пожеланиях нет старта, маршрут начнётся от центра города.");
                }
            }
            @Override public void onNothingSelected(AdapterView<?> parent) { }
        });
        updateCityArrow();
        mapButton.setOnClickListener(view -> openMap());
        startWalkButton.setOnClickListener(view -> startWalkOrContinue());
        resetRouteButton.setOnClickListener(view -> confirmRouteReset());
        editPointsButton.setOnClickListener(view -> loadPointEditor());
        moveUp.setOnClickListener(view -> moveSelectedPoint(-1));
        moveDown.setOnClickListener(view -> moveSelectedPoint(1));
        remove.setOnClickListener(view -> removeSelectedPoint());
        findPlaceButton.setOnClickListener(view -> searchPlaces());
        addPlaceButton.setOnClickListener(view -> addSelectedPlace());
        applyPointsButton.setOnClickListener(view -> applyPointChanges());
        applyCooldown();
        updateQueryEditActions();
        showLocationRebuildIfNeeded();
        beginAutomaticLocationDetection();
    }

    @Override public boolean dispatchTouchEvent(MotionEvent event) {
        if (event.getActionMasked() == MotionEvent.ACTION_DOWN) {
            View focused = getCurrentFocus();
            if (focused instanceof EditText) {
                int[] location = new int[2];
                focused.getLocationOnScreen(location);
                float x = event.getRawX();
                float y = event.getRawY();
                boolean outside = x < location[0] || x > location[0] + focused.getWidth()
                        || y < location[1] || y > location[1] + focused.getHeight();
                if (outside) {
                    focused.clearFocus();
                    InputMethodManager keyboard = (InputMethodManager)
                            getSystemService(INPUT_METHOD_SERVICE);
                    if (keyboard != null) {
                        keyboard.hideSoftInputFromWindow(focused.getWindowToken(), 0);
                    }
                }
            }
        }
        return super.dispatchTouchEvent(event);
    }

    private void addFilterStub(LinearLayout parent, String text) {
        Button chip = UiKit.button(this, text, UiKit.SOFT, UiKit.TEXT);
        chip.setTypeface(Typeface.DEFAULT, Typeface.NORMAL);
        chip.setTextSize(14);
        chip.setMinHeight(0);
        chip.setMinWidth(0);
        chip.setElevation(0f);
        chip.setStateListAnimator(null);
        chip.setPadding(UiKit.dp(this, 16), 0, UiKit.dp(this, 16), 0);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-2, -1);
        params.rightMargin = UiKit.dp(this, 8);
        parent.addView(chip, params);
    }

    private Button navigationTab(String text, int color) {
        Button tab = new Button(this);
        tab.setText(text);
        tab.setTextColor(color);
        tab.setTextSize(12);
        tab.setAllCaps(false);
        tab.setGravity(Gravity.CENTER);
        tab.setPadding(0, 0, 0, 0);
        tab.setMinHeight(0);
        tab.setMinWidth(0);
        tab.setBackgroundColor(0x00000000);
        return tab;
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
            locationStatus.setText("Локация не определена. Выберите доступный город в списке.");
            return;
        }
        if (startLat != null && startLon != null && !locationMatchesCity(cityId, startLat, startLon)) {
            clearCoordinatesKeepingCity();
            locationStatus.setText("Город выбран вручную. Если в пожеланиях нет старта, маршрут начнётся от центра города.");
        }
        boolean revise = routeId != null && cityId.equals(routeCityId) && !routeLocationDirty;
        String previous = lastSuccessfulResult;
        final String activeWalkBeforeChange = activeWalkIdForCurrentRoute();
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
            if (response.success && activeWalkBeforeChange != null) {
                try {
                    ApiClient.walkAction(activeWalkBeforeChange, owner, "STOP");
                } catch (Exception ignored) { }
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
                    queryEditMode = false;
                    persistQueryEditMode();
                    updateQueryEditActions();
                    if (activeWalkBeforeChange != null) clearActiveWalkState();
                    submit.setText("Изменить маршрут");
                    editPointsButton.setEnabled(true);
                    startWalkButton.setEnabled(true);
                    mapButton.setEnabled(true);
                    currentPoints.clear();
                    currentPoints.addAll(finalResponse.points);
                    pointEditor.setVisibility(View.GONE);
                    persistRouteState(text);
                    openMap();
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
                    if (finalRefreshedAfterConflict) {
                        refreshPointEditor();
                        editorStatus.setText(
                                "Маршрут уже изменился. Загружена актуальная версия — повторите правки.");
                    } else {
                        pointEditor.setVisibility(View.GONE);
                        foundPlaces.clear();
                        placeSearch.setText("");
                    }
                    persistRouteState(query.getText().toString().trim());
                    if (!finalRefreshedAfterConflict) openMap();
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
        returnToRouteButton.setEnabled(!busy);
        editPointsButton.setEnabled(!busy && routeId != null);
        startWalkButton.setEnabled(!busy && routeId != null);
        mapButton.setEnabled(!busy && routeId != null);
        resetRouteButton.setEnabled(!busy && routeId != null);
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
                returnToRouteButton.setEnabled(true);
                editPointsButton.setEnabled(routeId != null);
                startWalkButton.setEnabled(routeId != null);
                mapButton.setEnabled(routeId != null);
                resetRouteButton.setEnabled(routeId != null);
                findPlaceButton.setEnabled(true);
                addPlaceButton.setEnabled(!foundPlaces.isEmpty());
                applyPointsButton.setEnabled(!currentPoints.isEmpty());
            }
            return;
        }
        submit.setEnabled(false);
        returnToRouteButton.setEnabled(false);
        editPointsButton.setEnabled(false);
        startWalkButton.setEnabled(false);
        mapButton.setEnabled(false);
        resetRouteButton.setEnabled(false);
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
        queryEditMode = preferences.getBoolean("queryEditMode", false);
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
        out.putBoolean("queryEditMode", queryEditMode);
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
        if (locationTimeout != null) {
            uiHandler.removeCallbacks(locationTimeout);
            locationTimeout = null;
        }
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
            int requestedProviders = 0;
            if (gpsEnabled) {
                if (claimGeoAttempt()) {
                    locationManager.requestSingleUpdate(LocationManager.GPS_PROVIDER,
                            locationListener, Looper.getMainLooper());
                    requestedProviders++;
                }
            }
            if (networkEnabled) {
                if (claimGeoAttempt()) {
                    locationManager.requestSingleUpdate(LocationManager.NETWORK_PROVIDER,
                            locationListener, Looper.getMainLooper());
                    requestedProviders++;
                }
            }
            if (requestedProviders == 0) {
                locationListener = null;
                locationButton.setEnabled(true);
                locationStatus.setText("Геопозиция запрашивается не чаще двух раз в минуту. "
                        + "Повторите через " + geoRetryAfterSeconds() + " сек.");
                return;
            }
            locationTimeout = () -> {
                if (locationListener == null) {
                    locationTimeout = null;
                    return;
                }
                try { locationManager.removeUpdates(locationListener); }
                catch (SecurityException ignored) { }
                locationListener = null;
                locationTimeout = null;
                locationButton.setEnabled(true);
                if (!locationResolved && selectedCityId() == null) {
                    locationStatus.setText("Локация не определена. Выберите доступный город вручную.");
                } else if (!locationResolved) {
                    locationStatus.setText("Город определён по последней позиции. " +
                            "Если в пожеланиях нет старта, маршрут начнётся от центра города.");
                }
            };
            uiHandler.postDelayed(locationTimeout, 20_000L);
        } catch (SecurityException error) {
            if (locationManager != null && locationListener != null) {
                try { locationManager.removeUpdates(locationListener); }
                catch (SecurityException ignored) { }
                locationListener = null;
            }
            locationButton.setEnabled(true);
            clearLocationToUnknown();
            locationStatus.setText("Нет разрешения на геопозицию. Выберите город вручную.");
        }
    }

    private boolean claimGeoAttempt() {
        long now = System.currentTimeMillis();
        SharedPreferences throttle = getSharedPreferences("geo_attempt_throttle", MODE_PRIVATE);
        long previous = throttle.getLong("previous", 0L);
        long latest = throttle.getLong("latest", 0L);
        long cutoff = now - GEO_ATTEMPT_WINDOW_MILLIS;
        if (previous > now || latest > now) {
            previous = 0L;
            latest = 0L;
        }
        if (previous > cutoff) return false;
        if (latest > cutoff) {
            previous = latest;
            latest = now;
        } else {
            previous = 0L;
            latest = now;
        }
        throttle.edit().putLong("previous", previous).putLong("latest", latest).apply();
        return true;
    }

    private int geoRetryAfterSeconds() {
        long now = System.currentTimeMillis();
        SharedPreferences throttle = getSharedPreferences("geo_attempt_throttle", MODE_PRIVATE);
        long previous = throttle.getLong("previous", 0L);
        if (previous <= 0L || previous > now) return 1;
        return Math.max(1, (int) Math.ceil(
                (previous + GEO_ATTEMPT_WINDOW_MILLIS - now) / 1000.0));
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
        if (locationTimeout != null) {
            uiHandler.removeCallbacks(locationTimeout);
            locationTimeout = null;
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
        if (position == 1) return "tula";
        if (position == 2) return "vladimir";
        if (position == 3) return "moscow";
        if (position == 4) return "borovsk";
        return null;
    }

    private static int cityPosition(String cityId) {
        if ("tula".equals(cityId)) return 1;
        if ("vladimir".equals(cityId)) return 2;
        if ("moscow".equals(cityId)) return 3;
        if ("borovsk".equals(cityId)) return 4;
        return 0;
    }

    private static String cityName(String cityId) {
        if ("moscow".equals(cityId)) return "Москва";
        if ("vladimir".equals(cityId)) return "Владимир";
        if ("borovsk".equals(cityId)) return "Боровск";
        return "Тула";
    }

    private static String cityIdForLocation(double lat, double lon) {
        if (locationMatchesCity("borovsk", lat, lon)) return "borovsk";
        if (locationMatchesCity("moscow", lat, lon)) return "moscow";
        if (locationMatchesCity("vladimir", lat, lon)) return "vladimir";
        if (locationMatchesCity("tula", lat, lon)) return "tula";
        return null;
    }

    private static boolean locationMatchesCity(String cityId, double lat, double lon) {
        double centerLat = 54.1930, centerLon = 37.6178, limitKm = 50.0;
        if ("vladimir".equals(cityId)) { centerLat = 56.1291; centerLon = 40.4075; }
        if ("moscow".equals(cityId)) { centerLat = 55.7558; centerLon = 37.6173; limitKm = 80.0; }
        if ("borovsk".equals(cityId)) { centerLat = 55.2073; centerLon = 36.4833; limitKm = 25.0; }
        double latKm = (lat - centerLat) * 111.32;
        double lonKm = (lon - centerLon) * 111.32 * Math.cos(Math.toRadians(centerLat));
        return Math.sqrt(latKm * latKm + lonKm * lonKm) <= limitKm;
    }

    private void updateCityArrow() {
        if (cityArrow == null || city == null) return;
        cityArrow.setTextColor(city.getSelectedItemPosition() == 0
                ? UiKit.RED_SOFT : UiKit.MUTED);
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
        startActivityForResult(intent, ROUTE_SCREEN_REQUEST);
    }

    private void returnToCurrentRoute() {
        if (routeId == null || routeCityId == null || requestInFlight) return;
        String savedQuery = getPreferences(MODE_PRIVATE).getString("routeQuery", null);
        if (savedQuery != null) query.setText(savedQuery);
        if (lastSuccessfulResult != null) result.setText(lastSuccessfulResult);
        queryEditMode = false;
        persistQueryEditMode();
        updateQueryEditActions();
        String activeWalkId = activeWalkIdForCurrentRoute();
        if (activeWalkId != null) {
            openWalkMap(activeWalkId);
        } else {
            openMap();
        }
    }

    private String activeWalkIdForCurrentRoute() {
        if (routeId == null) return null;
        SharedPreferences walk = getSharedPreferences("active_walk", MODE_PRIVATE);
        String activeWalkId = walk.getString("walkId", null);
        String activeRouteId = walk.getString("routeId", null);
        return activeWalkId != null && routeId.equals(activeRouteId) ? activeWalkId : null;
    }

    private void clearActiveWalkState() {
        getSharedPreferences("active_walk", MODE_PRIVATE).edit().clear().apply();
    }

    private void persistQueryEditMode() {
        getPreferences(MODE_PRIVATE).edit().putBoolean("queryEditMode", queryEditMode).apply();
    }

    private void updateQueryEditActions() {
        if (returnToRouteButton == null) return;
        boolean visible = queryEditMode && routeId != null;
        returnToRouteButton.setVisibility(visible ? View.VISIBLE : View.GONE);
        submit.setText(routeId == null ? "Построить маршрут" : "Изменить маршрут");
    }

    private void startWalkOrContinue() {
        if (requestInFlight || routeId == null || routeCityId == null) return;
        SharedPreferences walk = getSharedPreferences("active_walk", MODE_PRIVATE);
        String activeWalkId = walk.getString("walkId", null);
        String activeRouteId = walk.getString("routeId", null);
        if (activeWalkId != null && routeId.equals(activeRouteId)) {
            openWalkMap(activeWalkId);
            return;
        }
        setNetworkBusy(true);
        result.setText("Запускаем прогулку…");
        final String requestedRouteId = routeId;
        final int requestedVersion = routeVersion;
        final String owner = sessionId();
        network.execute(() -> {
            ApiClient.WalkResult response;
            try {
                response = ApiClient.startWalk(
                        requestedRouteId, requestedVersion, owner);
            } catch (Exception exception) {
                response = new ApiClient.WalkResult(false,
                        "Не удалось запустить прогулку. Проверьте backend.", null, null,
                        0, 0, false, -1, null);
            }
            ApiClient.WalkResult finalResponse = response;
            runOnUiThread(() -> {
                if (isFinishing() || isDestroyed()) return;
                if (finalResponse.success) {
                    getSharedPreferences("active_walk", MODE_PRIVATE).edit()
                            .putString("walkId", finalResponse.walkId)
                            .putString("routeId", requestedRouteId)
                            .putInt("routeVersion", requestedVersion).apply();
                    startWalkButton.setText("Продолжить прогулку");
                    result.setText(lastSuccessfulResult == null ? finalResponse.message
                            : lastSuccessfulResult + "\n\n" + finalResponse.message);
                    openWalkMap(finalResponse.walkId);
                } else {
                    result.setText((lastSuccessfulResult == null ? "" :
                            lastSuccessfulResult + "\n\n") + finalResponse.message);
                }
                finishNetwork(0);
            });
        });
    }

    private void openWalkMap(String walkId) {
        Intent intent = new Intent(this, MapActivity.class);
        intent.putExtra(MapActivity.EXTRA_ROUTE_ID, routeId);
        intent.putExtra(MapActivity.EXTRA_CITY_ID, routeCityId);
        intent.putExtra(MapActivity.EXTRA_SESSION_ID, sessionId());
        intent.putExtra(MapActivity.EXTRA_WALK_ID, walkId);
        startActivityForResult(intent, ROUTE_SCREEN_REQUEST);
    }

    private void confirmRouteReset() {
        if (requestInFlight || routeId == null) return;
        new AlertDialog.Builder(this)
                .setTitle("Сбросить маршрут?")
                .setMessage("Запрос, точки и построенный маршрут будут удалены.")
                .setNegativeButton("Отмена", null)
                .setPositiveButton("Сбросить", (dialog, which) -> resetRoute())
                .show();
    }

    private void resetRoute() {
        final String requestedRouteId = routeId;
        final String owner = sessionId();
        setNetworkBusy(true);
        result.setText("Сбрасываем маршрут…");
        network.execute(() -> {
            ApiClient.Result response;
            try {
                response = ApiClient.deleteRoute(requestedRouteId, owner);
            } catch (Exception exception) {
                response = new ApiClient.Result(false,
                        "Backend недоступен: маршрут сброшен только в приложении.", null, 0);
            }
            ApiClient.Result finalResponse = response;
            runOnUiThread(() -> {
                if (isFinishing() || isDestroyed()) return;
                clearLocalRouteState(finalResponse.success
                        ? "Маршрут полностью сброшен. Можно составить новый."
                        : finalResponse.message);
                finishNetwork(0);
            });
        });
    }

    private void clearLocalRouteState(String message) {
        routeId = null;
        routeVersion = 0;
        routeCityId = null;
        lastSuccessfulResult = null;
        routeLocationDirty = false;
        queryEditMode = false;
        retryAllowedAtMillis = 0;
        currentPoints.clear();
        foundPlaces.clear();
        query.setText("");
        placeSearch.setText("");
        pointEditor.setVisibility(View.GONE);
        submit.setText("Построить маршрут");
        editPointsButton.setEnabled(false);
        startWalkButton.setEnabled(false);
        startWalkButton.setVisibility(View.GONE);
        mapButton.setEnabled(false);
        resetRouteButton.setVisibility(View.GONE);
        result.setText(message);
        getPreferences(MODE_PRIVATE).edit()
                .remove("routeId").remove("routeVersion").remove("routeCityId")
                .remove("lastSuccessfulResult").remove("routeQuery")
                .remove("routeLocationDirty").remove("queryEditMode").apply();
        clearActiveWalkState();
        updateQueryEditActions();
    }

    @Override protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != ROUTE_SCREEN_REQUEST || resultCode != RESULT_OK || data == null) return;
        String action = data.getStringExtra(MapActivity.EXTRA_RESULT_ACTION);
        if (MapActivity.ACTION_CANCEL_ROUTE.equals(action)) {
            clearLocalRouteState("Маршрут отменён. Можно составить новый.");
        } else if (MapActivity.ACTION_EDIT_QUERY.equals(action)) {
            queryEditMode = true;
            persistQueryEditMode();
            updateQueryEditActions();
            query.requestFocus();
            query.setSelection(query.getText().length());
            result.setText("Измените пожелания или вернитесь к текущему маршруту.");
        } else if (MapActivity.ACTION_EDIT_POINTS.equals(action)) {
            loadPointEditor();
        }
    }

    @Override protected void onResume() {
        super.onResume();
        if (startWalkButton == null) return;
        SharedPreferences walk = getSharedPreferences("active_walk", MODE_PRIVATE);
        String activeWalkId = walk.getString("walkId", null);
        String activeRouteId = walk.getString("routeId", null);
        boolean currentWalkActive = activeWalkId != null && routeId != null
                && routeId.equals(activeRouteId);
        startWalkButton.setText(currentWalkActive
                ? "Продолжить прогулку" : "Начать прогулку");
        if (currentWalkActive) {
            submit.setEnabled(!requestInFlight);
            returnToRouteButton.setEnabled(!requestInFlight);
            editPointsButton.setEnabled(false);
            resetRouteButton.setEnabled(false);
        } else if (!requestInFlight) {
            submit.setEnabled(true);
            editPointsButton.setEnabled(routeId != null);
            resetRouteButton.setEnabled(routeId != null);
        }
    }

    @Override protected void onDestroy() {
        if (locationTimeout != null) {
            uiHandler.removeCallbacks(locationTimeout);
            locationTimeout = null;
        }
        if (locationManager != null && locationListener != null) {
            locationManager.removeUpdates(locationListener);
            locationListener = null;
        }
        network.shutdownNow();
        super.onDestroy();
    }
}
