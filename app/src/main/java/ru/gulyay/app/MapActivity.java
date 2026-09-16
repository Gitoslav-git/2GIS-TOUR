package ru.gulyay.app;

import android.Manifest;
import android.app.AlertDialog;
import android.content.Context;
import android.content.pm.PackageManager;
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
    private LocationManager locationManager;
    private LocationListener locationListener;
    private boolean positionInFlight;

    @Override public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        restoredCamera = savedInstanceState != null;
        routeViewModel = new ViewModelProvider(this).get(RouteViewModel.class);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        int padding = (int) (12 * getResources().getDisplayMetrics().density);

        LinearLayout header = new LinearLayout(this);
        header.setGravity(Gravity.CENTER_VERTICAL);
        Button close = new Button(this);
        close.setText("Назад");
        close.setOnClickListener(view -> finish());
        header.addView(close);
        TextView title = new TextView(this);
        title.setText("Карта маршрута · 2ГИС");
        title.setTextSize(20);
        title.setPadding(padding, 0, 0, 0);
        header.addView(title, new LinearLayout.LayoutParams(0, -2, 1));
        root.addView(header);

        status = new TextView(this);
        status.setPadding(padding, padding / 2, padding, padding / 2);
        status.setText("Загружаем маршрут…");
        root.addView(status);

        LinearLayout walkControls = new LinearLayout(this);
        pauseResume = new Button(this);
        pauseResume.setText("Пауза");
        pauseResume.setEnabled(false);
        walkControls.addView(pauseResume, new LinearLayout.LayoutParams(0, -2, 1));
        stopWalk = new Button(this);
        stopWalk.setText("Завершить");
        stopWalk.setEnabled(false);
        walkControls.addView(stopWalk, new LinearLayout.LayoutParams(0, -2, 1));
        boolean walkMode = getIntent().getStringExtra(EXTRA_WALK_ID) != null;
        walkControls.setVisibility(walkMode ? View.VISIBLE : View.GONE);
        root.addView(walkControls);
        pauseResume.setOnClickListener(view -> {
            if (walk == null || !walk.success) return;
            sendWalkAction("PAUSED".equals(walk.status) ? "RESUME" : "PAUSE");
        });
        stopWalk.setOnClickListener(view -> confirmStopWalk());

        FrameLayout mapContainer = new FrameLayout(this);
        root.addView(mapContainer, new LinearLayout.LayoutParams(-1, 0, 1));
        setContentView(root);

        GulyayApplication application = (GulyayApplication) getApplication();
        if (application.sdkContext() == null) {
            TextView error = new TextView(this);
            error.setText(application.mapError());
            error.setTextSize(18);
            error.setGravity(Gravity.CENTER);
            error.setPadding(padding * 2, padding * 2, padding * 2, padding * 2);
            mapContainer.addView(error, new FrameLayout.LayoutParams(-1, -1));
            status.setText("Карта недоступна");
            route = routeViewModel.route;
            walk = routeViewModel.walk;
            if (route == null) loadRoute();
            else showRouteStatus();
            if (walkMode) {
                if (walk == null) loadWalk();
                else showWalkStatus();
            }
            return;
        }

        String cityId = getIntent().getStringExtra(EXTRA_CITY_ID);
        double[] center = "moscow".equals(cityId) ? new double[]{55.7558, 37.6173}
                : ("vladimir".equals(cityId) ? new double[]{56.1291, 40.4075}
                : new double[]{54.1930, 37.6178});
        MapOptions options = new MapOptions();
        options.setPosition(camera(center[0], center[1], 12.5f));
        mapView = new MapView(this, options);
        mapView.setId(R.id.route_map_view);
        getLifecycle().addObserver(mapView);
        mapContainer.addView(mapView, new FrameLayout.LayoutParams(-1, -1));
        mapView.getMapAsync(readyMap -> {
            map = readyMap;
            renderRoute();
            return Unit.INSTANCE;
        });
        route = routeViewModel.route;
        walk = routeViewModel.walk;
        if (route == null) {
            loadRoute();
        } else {
            showRouteStatus();
        }
        if (walkMode) {
            if (walk == null) loadWalk();
            else showWalkStatus();
        }
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
        status.setText("Версия " + route.routeVersion + " · точек: " +
                route.points.size() + (route.path.size() >= 2
                ? " · линия из геометрии Routing API 2ГИС"
                : " · геометрия пути отсутствует"));
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
        String pointName = "";
        if (route != null && walk.currentPointOrder > 0
                && walk.currentPointOrder <= route.points.size()) {
            pointName = "\nЦель: " + route.points.get(walk.currentPointOrder - 1).name;
        }
        status.setText(walk.message + pointName +
                "\nПрибытие: два точных измерения в радиусе 75 м с интервалом от 5 сек.");
        boolean active = "ACTIVE".equals(walk.status);
        boolean paused = "PAUSED".equals(walk.status);
        pauseResume.setEnabled(active || paused);
        pauseResume.setText(paused ? "Продолжить" : "Пауза");
        stopWalk.setEnabled(active || paused);
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
