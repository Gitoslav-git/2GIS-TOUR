package ru.gulyay.app;

import android.Manifest;
import android.app.AlertDialog;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Typeface;
import android.location.Location;
import android.location.LocationListener;
import android.location.LocationManager;
import android.os.Bundle;
import android.os.Looper;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import androidx.activity.ComponentActivity;
import androidx.lifecycle.ViewModel;
import androidx.lifecycle.ViewModelProvider;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import kotlin.Unit;
import ru.dgis.sdk.Color;
import ru.dgis.sdk.Duration;
import ru.dgis.sdk.coordinates.Bearing;
import ru.dgis.sdk.coordinates.GeoPoint;
import ru.dgis.sdk.coordinates.GeoPointExtraKt;
import ru.dgis.sdk.geometry.Elevation;
import ru.dgis.sdk.geometry.GeoPointWithElevation;
import ru.dgis.sdk.geometry.GeoPointWithElevationExtraKt;
import ru.dgis.sdk.map.Anchor;
import ru.dgis.sdk.map.AnimationMode;
import ru.dgis.sdk.map.CameraAnimationType;
import ru.dgis.sdk.map.CameraPosition;
import ru.dgis.sdk.map.Image;
import ru.dgis.sdk.map.ImagesKt;
import ru.dgis.sdk.map.LabelingPriority;
import ru.dgis.sdk.map.LogicalPixel;
import ru.dgis.sdk.map.Map;
import ru.dgis.sdk.map.MapObjectManager;
import ru.dgis.sdk.map.MapOptions;
import ru.dgis.sdk.map.MapView;
import ru.dgis.sdk.map.Marker;
import ru.dgis.sdk.map.MarkerOptions;
import ru.dgis.sdk.map.Opacity;
import ru.dgis.sdk.map.Polyline;
import ru.dgis.sdk.map.PolylineOptions;
import ru.dgis.sdk.map.TextStyle;
import ru.dgis.sdk.map.Tilt;
import ru.dgis.sdk.map.ZIndex;
import ru.dgis.sdk.map.Zoom;

public final class MapActivity extends ComponentActivity {
    static final String EXTRA_ROUTE_ID = "routeId";
    static final String EXTRA_CITY_ID = "cityId";
    static final String EXTRA_SESSION_ID = "sessionId";
    static final String EXTRA_WALK_ID = "walkId";
    static final String EXTRA_USER_LAT = "userLat";
    static final String EXTRA_USER_LON = "userLon";
    static final String EXTRA_RESULT_ACTION = "resultAction";
    static final String ACTION_CANCEL_ROUTE = "cancelRoute";
    static final String ACTION_EDIT_QUERY = "editQuery";
    static final String ACTION_EDIT_POINTS = "editPoints";

    private final ExecutorService network = Executors.newSingleThreadExecutor();
    private TextView status;
    private MapView mapView;
    private Map map;
    private MapObjectManager objects;
    private ApiClient.Result route;
    private ApiClient.WalkResult walk;
    private RouteViewModel routeViewModel;
    private boolean restoredCamera;
    private Button pauseResume;
    private Button stopWalk;
    private Button primaryAction;
    private Button editQuery;
    private Button editPoints;
    private TextView screenTitle;
    private TextView routeSummary;
    private TextView mapRouteSummary;
    private LinearLayout pointList;
    private boolean startingWalk;
    private LocationManager locationManager;
    private LocationListener locationListener;
    private boolean positionInFlight;

    @Override public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        restoredCamera = savedInstanceState != null;
        routeViewModel = new ViewModelProvider(this).get(RouteViewModel.class);

        FrameLayout root = new FrameLayout(this);
        LinearLayout page = new LinearLayout(this);
        page.setOrientation(LinearLayout.VERTICAL);
        root.addView(page, new FrameLayout.LayoutParams(-1, -1));
        boolean compact = getResources().getConfiguration().screenHeightDp <= 720;

        FrameLayout mapContainer = new FrameLayout(this);
        mapContainer.setBackground(UiKit.rounded(UiKit.MAP, 0, this));
        page.addView(mapContainer, new LinearLayout.LayoutParams(-1, 0, compact ? 0.47f : 0.54f));
        TextView mapPlaceholder = UiKit.label(this,
                "Карта маршрута\nЗдесь появится фрагмент 2ГИС", 17, UiKit.MUTED);
        mapPlaceholder.setGravity(Gravity.CENTER);
        mapContainer.addView(mapPlaceholder, new FrameLayout.LayoutParams(-1, -1));
        mapRouteSummary = UiKit.label(this, "Маршрут готов", 16, UiKit.TEXT);
        mapRouteSummary.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        mapRouteSummary.setPadding(UiKit.dp(this, 18), UiKit.dp(this, 12),
                UiKit.dp(this, 18), UiKit.dp(this, 12));
        mapRouteSummary.setBackground(UiKit.rounded(0xF2FFFFFF, 20, this));
        FrameLayout.LayoutParams mapSummaryParams = new FrameLayout.LayoutParams(
                -1, -2, Gravity.BOTTOM);
        mapSummaryParams.setMargins(UiKit.dp(this, 14), 0, UiKit.dp(this, 14),
                UiKit.dp(this, 12));
        mapContainer.addView(mapRouteSummary, mapSummaryParams);

        LinearLayout sheet = new LinearLayout(this);
        sheet.setOrientation(LinearLayout.VERTICAL);
        sheet.setPadding(UiKit.dp(this, 16), UiKit.dp(this, compact ? 7 : 9),
                UiKit.dp(this, 16), UiKit.dp(this, compact ? 8 : 12));
        sheet.setBackground(UiKit.rounded(0xFFFFFFFF, 26, this));
        page.addView(sheet, new LinearLayout.LayoutParams(-1, 0, compact ? 0.53f : 0.46f));

        TextView handle = UiKit.label(this, "", 1, 0x00000000);
        handle.setBackground(UiKit.rounded(0xFFC7CDCA, 3, this));
        LinearLayout.LayoutParams handleParams = new LinearLayout.LayoutParams(
                UiKit.dp(this, 42), UiKit.dp(this, 5));
        handleParams.gravity = Gravity.CENTER_HORIZONTAL;
        handleParams.bottomMargin = UiKit.dp(this, compact ? 5 : 8);
        sheet.addView(handle, handleParams);

        TextView nextLabel = UiKit.label(this, "ПЕРВАЯ ТОЧКА", 12, UiKit.GREEN_DARK);
        nextLabel.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        sheet.addView(nextLabel);
        LinearLayout pointHero = new LinearLayout(this);
        pointHero.setGravity(Gravity.CENTER_VERTICAL);
        routeSummary = UiKit.label(this, "Загружаем маршрут…", compact ? 19 : 22, UiKit.TEXT);
        routeSummary.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        routeSummary.setMaxLines(2);
        routeSummary.setEllipsize(android.text.TextUtils.TruncateAt.END);
        pointHero.addView(routeSummary, new LinearLayout.LayoutParams(0, -2, 1));
        TextView photo = UiKit.label(this, "Фото", 11, UiKit.MUTED);
        photo.setGravity(Gravity.CENTER);
        photo.setBackground(UiKit.rounded(0xFFE5E9E6, 14, this));
        pointHero.addView(photo, new LinearLayout.LayoutParams(
                UiKit.dp(this, compact ? 58 : 72), UiKit.dp(this, compact ? 46 : 56)));
        sheet.addView(pointHero, new LinearLayout.LayoutParams(-1,
                UiKit.dp(this, compact ? 50 : 60)));

        status = UiKit.label(this, "Строим детали прогулки…", 14, UiKit.MUTED);
        status.setGravity(Gravity.CENTER_VERTICAL);
        status.setPadding(UiKit.dp(this, 14), 0, UiKit.dp(this, 14), 0);
        status.setBackground(UiKit.rounded(0xFFEAF9EF, 12, this));
        LinearLayout.LayoutParams statusParams = new LinearLayout.LayoutParams(-1,
                UiKit.dp(this, compact ? 40 : 46));
        statusParams.topMargin = UiKit.dp(this, 4);
        statusParams.bottomMargin = UiKit.dp(this, 4);
        sheet.addView(status, statusParams);
        pointList = new LinearLayout(this);
        pointList.setOrientation(LinearLayout.VERTICAL);
        sheet.addView(pointList, new LinearLayout.LayoutParams(-1, 0, 1));

        LinearLayout actions = new LinearLayout(this);
        actions.setGravity(Gravity.CENTER_VERTICAL);
        editQuery = compactAction("Изменить маршрут");
        editPoints = compactAction("Редактировать точки");
        primaryAction = UiKit.button(this, "▶", UiKit.GREEN, 0xFFFFFFFF);
        primaryAction.setTextSize(22);
        LinearLayout.LayoutParams editActionParams = new LinearLayout.LayoutParams(0,
                UiKit.dp(this, compact ? 48 : 54), 1);
        editActionParams.rightMargin = UiKit.dp(this, 7);
        actions.addView(editQuery, editActionParams);
        LinearLayout.LayoutParams pointsActionParams = new LinearLayout.LayoutParams(0,
                UiKit.dp(this, compact ? 48 : 54), 1);
        pointsActionParams.rightMargin = UiKit.dp(this, 7);
        actions.addView(editPoints, pointsActionParams);
        actions.addView(primaryAction, new LinearLayout.LayoutParams(
                UiKit.dp(this, compact ? 52 : 58), UiKit.dp(this, compact ? 48 : 54)));
        sheet.addView(actions);
        pauseResume = UiKit.button(this, "Пауза", UiKit.SOFT, UiKit.TEXT);
        pauseResume.setVisibility(View.GONE);
        stopWalk = primaryAction;

        LinearLayout topBar = new LinearLayout(this);
        topBar.setGravity(Gravity.CENTER_VERTICAL);
        topBar.setPadding(UiKit.dp(this, 16), UiKit.dp(this, 20),
                UiKit.dp(this, 16), 0);
        screenTitle = UiKit.label(this, "Маршрут построен", 17, UiKit.TEXT);
        screenTitle.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        screenTitle.setPadding(UiKit.dp(this, 16), UiKit.dp(this, 10),
                UiKit.dp(this, 16), UiKit.dp(this, 10));
        screenTitle.setBackground(UiKit.rounded(0xF2FFFFFF, 18, this));
        topBar.addView(screenTitle, new LinearLayout.LayoutParams(0, -2, 1));
        Button close = UiKit.button(this, "×", 0xF2FFFFFF, UiKit.TEXT);
        close.setTextSize(24);
        LinearLayout.LayoutParams closeParams = new LinearLayout.LayoutParams(
                UiKit.dp(this, 50), UiKit.dp(this, 50));
        closeParams.leftMargin = UiKit.dp(this, 10);
        topBar.addView(close, closeParams);
        root.addView(topBar, new FrameLayout.LayoutParams(-1, -2, Gravity.TOP));
        setContentView(root);

        close.setOnClickListener(view -> confirmCancelRoute());
        editQuery.setOnClickListener(view -> returnForEdit(ACTION_EDIT_QUERY));
        editPoints.setOnClickListener(view -> returnForEdit(ACTION_EDIT_POINTS));
        primaryAction.setOnClickListener(view -> {
            if (walk != null && walk.success && ("ACTIVE".equals(walk.status)
                    || "PAUSED".equals(walk.status))) confirmCancelRoute();
            else startWalk();
        });
        pauseResume.setOnClickListener(view -> {
            if (walk != null && walk.success) {
                sendWalkAction("PAUSED".equals(walk.status) ? "RESUME" : "PAUSE");
            }
        });

        boolean walkMode = getIntent().getStringExtra(EXTRA_WALK_ID) != null;
        GulyayApplication application = (GulyayApplication) getApplication();
        if (application.sdkContext() == null) {
            mapPlaceholder.setText("Карта 2ГИС пока недоступна\nМаршрут и точки работают без неё");
        } else {
            String cityId = getIntent().getStringExtra(EXTRA_CITY_ID);
            double[] center = "moscow".equals(cityId) ? new double[]{55.7558, 37.6173}
                    : ("vladimir".equals(cityId) ? new double[]{56.1291, 40.4075}
                    : new double[]{54.1930, 37.6178});
            MapOptions options = new MapOptions();
            options.setPosition(camera(center[0], center[1], 12.5f));
            mapView = new MapView(this, options);
            mapView.setId(R.id.route_map_view);
            getLifecycle().addObserver(mapView);
            mapContainer.addView(mapView, 0, new FrameLayout.LayoutParams(-1, -1));
            mapView.getMapAsync(readyMap -> {
                map = readyMap;
                renderRoute();
                return Unit.INSTANCE;
            });
        }
        route = routeViewModel.route;
        walk = routeViewModel.walk;
        if (route == null) loadRoute(); else showRouteStatus();
        if (walkMode) {
            if (walk == null) loadWalk(); else showWalkStatus();
        }
    }

    private Button compactAction(String text) {
        Button button = UiKit.button(this, text, 0xFFFFFFFF, UiKit.GREEN_DARK);
        button.setTextSize(11);
        button.setPadding(UiKit.dp(this, 5), 0, UiKit.dp(this, 5), 0);
        button.setMinWidth(0);
        button.setMinHeight(0);
        button.setBackground(UiKit.bordered(0xFFFFFFFF, UiKit.GREEN, 14, this));
        return button;
    }

    private void loadRoute() {
        String routeId = getIntent().getStringExtra(EXTRA_ROUTE_ID);
        String cityId = getIntent().getStringExtra(EXTRA_CITY_ID);
        String sessionId = getIntent().getStringExtra(EXTRA_SESSION_ID);
        if (routeId == null || cityId == null || sessionId == null) {
            status.setText("Не переданы данные текущего маршрута.");
            return;
        }
        network.execute(() -> {
            ApiClient.Result response;
            try {
                response = ApiClient.getRoute(routeId, cityId, sessionId);
            } catch (Exception error) {
                response = new ApiClient.Result(false,
                        "Не удалось загрузить маршрут с backend.", null, 0);
            }
            ApiClient.Result finalResponse = response;
            runOnUiThread(() -> {
                if (isFinishing() || isDestroyed()) return;
                route = finalResponse;
                if (!route.success) {
                    status.setText(route.message);
                    return;
                }
                routeViewModel.route = route;
                showRouteStatus();
                renderRoute();
                syncLocationTracking();
            });
        });
    }

    private void showRouteStatus() {
        if (walk != null && walk.success) {
            showWalkStatus();
            return;
        }
        if (route == null || !route.success) return;
        screenTitle.setText("Прогулка по " + cityName() + "\nМаршрут построен");
        routeSummary.setText(route.points.isEmpty() ? "Маршрут" : route.points.get(0).name);
        String time = route.totalMinutes > 0 ? route.totalMinutes + " мин" : "время рассчитано";
        String distance = route.totalDistanceMeters > 0
                ? String.format(java.util.Locale.US, " • %.1f км", route.totalDistanceMeters / 1000.0)
                : "";
        status.setText("◷  " + time + "                   ●  " + route.points.size() + " места");
        mapRouteSummary.setText("🚶  Маршрут готов\n" + route.points.size() + " места • "
                + time + distance);
        primaryAction.setText("▶");
        primaryAction.setTextColor(0xFFFFFFFF);
        primaryAction.setBackground(UiKit.rounded(UiKit.GREEN, 14, this));
        editQuery.setEnabled(true);
        editPoints.setEnabled(true);
        renderPointList(0);
    }

    private String cityName() {
        String cityId = getIntent().getStringExtra(EXTRA_CITY_ID);
        return "moscow".equals(cityId) ? "Москве" :
                ("vladimir".equals(cityId) ? "Владимиру" : "Туле");
    }

    private void renderPointList(int currentOrder) {
        pointList.removeAllViews();
        if (route == null || route.points.isEmpty()) return;
        int start = currentOrder > 0 ? currentOrder : 1;
        int end = Math.min(route.points.size(), start + 3);
        for (int i = start; i < end; i++) {
            ApiClient.PlaceOption point = route.points.get(i);
            LinearLayout row = new LinearLayout(this);
            row.setGravity(Gravity.CENTER_VERTICAL);
            row.setPadding(0, UiKit.dp(this, 2), 0, UiKit.dp(this, 2));
            TextView number = UiKit.label(this, String.valueOf(i + 1), 14, 0xFFFFFFFF);
            number.setGravity(Gravity.CENTER);
            number.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
            number.setBackground(UiKit.rounded(0xFFE9F8EE, 20, this));
            number.setTextColor(UiKit.GREEN_DARK);
            row.addView(number, new LinearLayout.LayoutParams(
                    UiKit.dp(this, 32), UiKit.dp(this, 32)));
            String suffix = point.food ? " • заведение" : "";
            if (i == end - 1 && end < route.points.size()) {
                suffix += "  • ещё " + (route.points.size() - end);
            }
            TextView name = UiKit.label(this, point.name + suffix, 13, UiKit.TEXT);
            name.setMaxLines(2);
            name.setEllipsize(android.text.TextUtils.TruncateAt.END);
            name.setPadding(UiKit.dp(this, 12), 0, UiKit.dp(this, 8), 0);
            row.addView(name, new LinearLayout.LayoutParams(0, -2, 1));
            pointList.addView(row, new LinearLayout.LayoutParams(-1, 0, 1));
        }
    }

    private void startWalk() {
        if (startingWalk || route == null || !route.success) return;
        startingWalk = true;
        primaryAction.setEnabled(false);
        status.setText("Запускаем прогулку…");
        String routeId = getIntent().getStringExtra(EXTRA_ROUTE_ID);
        String sessionId = getIntent().getStringExtra(EXTRA_SESSION_ID);
        network.execute(() -> {
            ApiClient.WalkResult response;
            try {
                response = ApiClient.startWalk(routeId, route.routeVersion, sessionId);
            } catch (Exception error) {
                response = new ApiClient.WalkResult(false,
                        "Не удалось запустить прогулку. Проверьте backend.", null, null,
                        0, 0, false, -1, null);
            }
            ApiClient.WalkResult finalResponse = response;
            runOnUiThread(() -> {
                startingWalk = false;
                primaryAction.setEnabled(true);
                if (isFinishing() || isDestroyed()) return;
                if (!finalResponse.success) {
                    status.setText(finalResponse.message);
                    return;
                }
                walk = finalResponse;
                routeViewModel.walk = walk;
                getSharedPreferences("active_walk", MODE_PRIVATE).edit()
                        .putString("walkId", walk.walkId)
                        .putString("routeId", routeId).apply();
                showWalkStatus();
                syncLocationTracking();
            });
        });
    }

    private void loadWalk() {
        String walkId = getIntent().getStringExtra(EXTRA_WALK_ID);
        String sessionId = getIntent().getStringExtra(EXTRA_SESSION_ID);
        if (walkId == null || sessionId == null) return;
        network.execute(() -> {
            ApiClient.WalkResult response;
            try {
                response = ApiClient.getWalk(walkId, sessionId);
            } catch (Exception error) {
                response = new ApiClient.WalkResult(false,
                        "Не удалось загрузить прохождение с backend.", null, null,
                        0, 0, false, -1, null);
            }
            ApiClient.WalkResult finalResponse = response;
            runOnUiThread(() -> {
                if (isFinishing() || isDestroyed()) return;
                walk = finalResponse;
                if (!walk.success) {
                    status.setText(walk.message);
                    clearActiveWalk();
                    return;
                }
                routeViewModel.walk = walk;
                showWalkStatus();
                syncLocationTracking();
            });
        });
    }

    private void showWalkStatus() {
        if (walk == null || !walk.success) return;
        String pointName = "Следующая точка";
        if (route != null && walk.currentPointOrder > 0
                && walk.currentPointOrder <= route.points.size()) {
            pointName = route.points.get(walk.currentPointOrder - 1).name;
        }
        screenTitle.setText("Прогулка по " + cityName() + "\nМаршрут запущен");
        routeSummary.setText(pointName);
        status.setText("◷  Осталось ≈" + walk.remainingMinutes + " мин"
                + "              ●  точка " + walk.currentPointOrder);
        mapRouteSummary.setText("🚶  Маршрут запущен\nСледующая точка: "
                + walk.currentPointOrder + " • радиус 75 м");
        renderPointList(walk.currentPointOrder);
        boolean active = "ACTIVE".equals(walk.status);
        boolean paused = "PAUSED".equals(walk.status);
        pauseResume.setEnabled(active || paused);
        pauseResume.setText(paused ? "Продолжить" : "Пауза");
        stopWalk.setEnabled(active || paused);
        primaryAction.setText("×");
        primaryAction.setTextColor(0xFFFFFFFF);
        primaryAction.setBackground(UiKit.rounded(UiKit.RED, 14, this));
        editQuery.setEnabled(false);
        editPoints.setEnabled(false);
        if ("COMPLETED".equals(walk.status) || "STOPPED".equals(walk.status)) {
            clearActiveWalk();
        }
    }

    private void syncLocationTracking() {
        if (walk == null || !walk.success || !"ACTIVE".equals(walk.status)) {
            stopLocationTracking();
            return;
        }
        if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION)
                != PackageManager.PERMISSION_GRANTED
                && checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION)
                != PackageManager.PERMISSION_GRANTED) {
            status.append("\nГеопозиция запрещена — автоматическая отметка точки недоступна.");
            return;
        }
        if (locationListener != null) return;
        locationManager = (LocationManager) getSystemService(Context.LOCATION_SERVICE);
        locationListener = new LocationListener() {
            @Override public void onLocationChanged(Location location) {
                sendPosition(location);
            }
            @Override public void onProviderDisabled(String provider) { }
            @Override public void onProviderEnabled(String provider) { }
            @Override public void onStatusChanged(String provider, int value, Bundle extras) { }
        };
        try {
            boolean requested = false;
            if (locationManager.isProviderEnabled(LocationManager.GPS_PROVIDER)) {
                locationManager.requestLocationUpdates(LocationManager.GPS_PROVIDER,
                        5000L, 0f, locationListener, Looper.getMainLooper());
                requested = true;
            }
            if (locationManager.isProviderEnabled(LocationManager.NETWORK_PROVIDER)) {
                locationManager.requestLocationUpdates(LocationManager.NETWORK_PROVIDER,
                        5000L, 0f, locationListener, Looper.getMainLooper());
                requested = true;
            }
            if (!requested) {
                stopLocationTracking();
                status.append("\nГеопозиция выключена — автоматическая отметка точки недоступна.");
            }
        } catch (SecurityException error) {
            stopLocationTracking();
            status.append("\nНе удалось получить геопозицию для прохождения.");
        }
    }

    private void sendPosition(Location location) {
        if (positionInFlight || walk == null || !"ACTIVE".equals(walk.status)) return;
        positionInFlight = true;
        String walkId = walk.walkId;
        String sessionId = getIntent().getStringExtra(EXTRA_SESSION_ID);
        double accuracy = location.hasAccuracy() ? location.getAccuracy() : 100.0;
        network.execute(() -> {
            ApiClient.WalkResult response;
            try {
                response = ApiClient.sendWalkPosition(
                        walkId, sessionId, location.getLatitude(), location.getLongitude(),
                        accuracy, System.currentTimeMillis());
            } catch (Exception error) {
                response = new ApiClient.WalkResult(false,
                        "Не удалось передать геопозицию. Проверьте backend.", walkId,
                        walk.status, walk.currentPointOrder, walk.remainingMinutes,
                        false, -1, null);
            }
            ApiClient.WalkResult finalResponse = response;
            runOnUiThread(() -> {
                positionInFlight = false;
                if (isFinishing() || isDestroyed()) return;
                if (!finalResponse.success) {
                    status.setText(finalResponse.message);
                    return;
                }
                walk = finalResponse;
                routeViewModel.walk = walk;
                showWalkStatus();
                syncLocationTracking();
            });
        });
    }

    private void sendWalkAction(String action) {
        if (walk == null || !walk.success) return;
        pauseResume.setEnabled(false);
        stopWalk.setEnabled(false);
        String sessionId = getIntent().getStringExtra(EXTRA_SESSION_ID);
        network.execute(() -> {
            ApiClient.WalkResult response;
            try {
                response = ApiClient.walkAction(walk.walkId, sessionId, action);
            } catch (Exception error) {
                response = new ApiClient.WalkResult(false,
                        "Не удалось изменить состояние прогулки.", walk.walkId,
                        walk.status, walk.currentPointOrder, walk.remainingMinutes,
                        false, -1, null);
            }
            ApiClient.WalkResult finalResponse = response;
            runOnUiThread(() -> {
                if (isFinishing() || isDestroyed()) return;
                if (!finalResponse.success) {
                    status.setText(finalResponse.message);
                    boolean controllable = "ACTIVE".equals(walk.status)
                            || "PAUSED".equals(walk.status);
                    pauseResume.setEnabled(controllable);
                    stopWalk.setEnabled(controllable);
                    return;
                }
                walk = finalResponse;
                routeViewModel.walk = walk;
                showWalkStatus();
                syncLocationTracking();
            });
        });
    }

    private void confirmStopWalk() {
        if (walk == null || !("ACTIVE".equals(walk.status) || "PAUSED".equals(walk.status))) {
            return;
        }
        new AlertDialog.Builder(this)
                .setTitle("Завершить прогулку?")
                .setMessage("Автоматическое прохождение будет остановлено.")
                .setNegativeButton("Отмена", null)
                .setPositiveButton("Завершить", (dialog, which) -> sendWalkAction("STOP"))
                .show();
    }

    private void returnForEdit(String action) {
        Intent data = new Intent();
        data.putExtra(EXTRA_RESULT_ACTION, action);
        setResult(RESULT_OK, data);
        finish();
    }

    private void confirmCancelRoute() {
        if (startingWalk) return;
        new AlertDialog.Builder(this)
                .setTitle("Отменить маршрут?")
                .setMessage("Текущий маршрут будет полностью сброшен.")
                .setNegativeButton("Оставить", null)
                .setPositiveButton("Отменить маршрут", (dialog, which) -> cancelRoute())
                .show();
    }

    private void cancelRoute() {
        startingWalk = true;
        primaryAction.setEnabled(false);
        editQuery.setEnabled(false);
        editPoints.setEnabled(false);
        status.setText("Отменяем маршрут…");
        String routeId = getIntent().getStringExtra(EXTRA_ROUTE_ID);
        String sessionId = getIntent().getStringExtra(EXTRA_SESSION_ID);
        network.execute(() -> {
            try {
                if (walk != null && walk.success && ("ACTIVE".equals(walk.status)
                        || "PAUSED".equals(walk.status))) {
                    ApiClient.walkAction(walk.walkId, sessionId, "STOP");
                }
            } catch (Exception ignored) { }
            try { ApiClient.deleteRoute(routeId, sessionId); }
            catch (Exception ignored) { }
            runOnUiThread(() -> {
                clearActiveWalk();
                Intent data = new Intent();
                data.putExtra(EXTRA_RESULT_ACTION, ACTION_CANCEL_ROUTE);
                setResult(RESULT_OK, data);
                finish();
            });
        });
    }

    @Override public void onBackPressed() {
        confirmCancelRoute();
    }

    private void stopLocationTracking() {
        if (locationManager != null && locationListener != null) {
            try { locationManager.removeUpdates(locationListener); }
            catch (SecurityException ignored) { }
        }
        locationListener = null;
    }

    private void clearActiveWalk() {
        getSharedPreferences("active_walk", MODE_PRIVATE).edit().clear().apply();
        stopLocationTracking();
    }

    private void renderRoute() {
        if (map == null || route == null || !route.success) return;
        if (objects == null) objects = new MapObjectManager(map, null);
        else objects.removeAll();

        GulyayApplication application = (GulyayApplication) getApplication();
        Image routeIcon = ImagesKt.imageFromResource(
                application.sdkContext(), R.drawable.route_marker, null);
        for (int i = 0; i < route.points.size(); i++) {
            ApiClient.PlaceOption point = route.points.get(i);
            if (!Double.isFinite(point.lat) || !Double.isFinite(point.lon)) continue;
            MarkerOptions options = markerOptions(point.lat, point.lon, routeIcon,
                    (i + 1) + ". " + point.name, i + 2);
            objects.addObject(new Marker(options));
        }

        if (route.path.size() >= 2) {
            List<GeoPoint> geometry = new ArrayList<>();
            for (ApiClient.GeoCoordinate coordinate : route.path) {
                geometry.add(GeoPointExtraKt.GeoPoint(coordinate.lat, coordinate.lon));
            }
            PolylineOptions line = new PolylineOptions(
                    geometry, new LogicalPixel(5f), new Color(0xFF00A88F),
                    0.0, null, null, true, "route", new ZIndex(1), null, null);
            objects.addObject(new Polyline(line));
        }

        double userLat = getIntent().getDoubleExtra(EXTRA_USER_LAT, Double.NaN);
        double userLon = getIntent().getDoubleExtra(EXTRA_USER_LON, Double.NaN);
        if (Double.isFinite(userLat) && Double.isFinite(userLon)) {
            Image userIcon = ImagesKt.imageFromResource(
                    application.sdkContext(), R.drawable.user_marker, null);
            objects.addObject(new Marker(markerOptions(
                    userLat, userLon, userIcon, "Вы здесь", route.points.size() + 3)));
        }

        if (!restoredCamera && !route.path.isEmpty()) {
            double[] bounds = routeBounds(route.path);
            map.getCamera().move(camera(bounds[0], bounds[1], (float) bounds[2]),
                    Duration.ofMilliseconds(0), CameraAnimationType.LINEAR);
        }
    }

    private static MarkerOptions markerOptions(double lat, double lon, Image icon,
                                                String text, int zIndex) {
        GeoPointWithElevation position = GeoPointWithElevationExtraKt.GeoPointWithElevation(
                lat, lon, new Elevation());
        return new MarkerOptions(
                position, icon, null, new Anchor(0.5f, 1f), text, (TextStyle) null,
                new Opacity(1f), true, false, new LogicalPixel(32f), text,
                new ZIndex(zIndex), new LabelingPriority((byte) 1), true,
                null, AnimationMode.NORMAL, false);
    }

    private static CameraPosition camera(double lat, double lon, float zoom) {
        return new CameraPosition(GeoPointExtraKt.GeoPoint(lat, lon), new Zoom(zoom),
                new Tilt(0f), new Bearing(0.0));
    }

    private static double[] routeBounds(List<ApiClient.GeoCoordinate> path) {
        double minLat = 90, maxLat = -90, minLon = 180, maxLon = -180;
        for (ApiClient.GeoCoordinate coordinate : path) {
            minLat = Math.min(minLat, coordinate.lat);
            maxLat = Math.max(maxLat, coordinate.lat);
            minLon = Math.min(minLon, coordinate.lon);
            maxLon = Math.max(maxLon, coordinate.lon);
        }
        double span = Math.max(maxLat - minLat, (maxLon - minLon) *
                Math.cos(Math.toRadians((minLat + maxLat) / 2.0)));
        double zoom = span < 0.004 ? 15.5 : span < 0.01 ? 14.5 :
                span < 0.025 ? 13.5 : span < 0.06 ? 12.5 : 11.5;
        return new double[]{(minLat + maxLat) / 2.0, (minLon + maxLon) / 2.0, zoom};
    }

    @Override protected void onDestroy() {
        stopLocationTracking();
        network.shutdownNow();
        super.onDestroy();
    }

    public static final class RouteViewModel extends ViewModel {
        ApiClient.Result route;
        ApiClient.WalkResult walk;
    }
}
