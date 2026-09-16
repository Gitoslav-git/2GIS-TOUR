package ru.gulyay.app;

import android.os.Bundle;
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
    static final String EXTRA_USER_LAT = "userLat";
    static final String EXTRA_USER_LON = "userLon";

    private final ExecutorService network = Executors.newSingleThreadExecutor();
    private TextView status;
    private MapView mapView;
    private Map map;
    private MapObjectManager objects;
    private ApiClient.Result route;
    private RouteViewModel routeViewModel;
    private boolean restoredCamera;

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
            return;
        }

        String cityId = getIntent().getStringExtra(EXTRA_CITY_ID);
        double[] center = "vladimir".equals(cityId)
                ? new double[]{56.1291, 40.4075} : new double[]{54.1930, 37.6178};
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
        if (route == null) {
            loadRoute();
        } else {
            showRouteStatus();
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
            });
        });
    }

    private void showRouteStatus() {
        status.setText("Версия " + route.routeVersion + " · точек: " +
                route.points.size() + (route.path.size() >= 2
                ? " · линия из геометрии Routing API 2ГИС"
                : " · геометрия пути отсутствует"));
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
        network.shutdownNow();
        super.onDestroy();
    }

    public static final class RouteViewModel extends ViewModel {
        ApiClient.Result route;
    }
}
