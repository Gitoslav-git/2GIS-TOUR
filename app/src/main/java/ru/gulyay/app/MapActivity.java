package ru.gulyay.app;

import android.Manifest;
import android.app.ActivityManager;
import android.app.AlertDialog;
import android.app.Dialog;
import android.content.ActivityNotFoundException;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.Typeface;
import android.location.Location;
import android.location.LocationListener;
import android.location.LocationManager;
import android.net.Uri;
import android.os.Bundle;
import android.os.Debug;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.text.Editable;
import android.text.SpannableString;
import android.text.Spanned;
import android.text.TextWatcher;
import android.text.style.RelativeSizeSpan;
import android.util.Log;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.Window;
import android.view.WindowManager;
import android.view.inputmethod.InputMethodManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;
import androidx.activity.ComponentActivity;
import androidx.lifecycle.ViewModel;
import androidx.lifecycle.ViewModelProvider;
import java.util.ArrayList;
import java.util.Collections;
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
    private static final int ROUTE_CHAT_REQUEST = 207;
    private static final String MEMORY_LOG = "GulyayMapMemory";
    private static final String GEO_LOG = "GulyayGeoWalk";
    private static final int ARRIVAL_RADIUS_METERS = 75;
    private static final int EXIT_RADIUS_METERS = 115;
    static final String EXTRA_ROUTE_ID = "routeId";
    static final String EXTRA_CITY_ID = "cityId";
    static final String EXTRA_SESSION_ID = "sessionId";
    static final String EXTRA_WALK_ID = "walkId";
    static final String EXTRA_USER_LAT = "userLat";
    static final String EXTRA_USER_LON = "userLon";
    static final String EXTRA_RESULT_ACTION = "resultAction";
    static final String EXTRA_WALK_STATUS = "walkStatus";
    static final String EXTRA_ROUTE_SNAPSHOT = "routeSnapshot";
    static final String EXTRA_ROUTE_VERSION = "routeVersion";
    static final String EXTRA_HISTORY_READ_ONLY = "historyReadOnly";
    static final String EXTRA_WALK_STATUS_UNCONFIRMED = "walkStatusUnconfirmed";
    static final String ACTION_CANCEL_ROUTE = "cancelRoute";
    static final String ACTION_EDIT_QUERY = "editQuery";
    static final String ACTION_EDIT_POINTS = "editPoints";
    static final String ACTION_WALK_STOPPED = "walkStopped";
    private static final String ROUTE_LIFECYCLE_PREFERENCES = "route_lifecycle";
    private static final String FINISHED_ROUTE_ID = "finishedRouteId";

    private final ExecutorService network = Executors.newSingleThreadExecutor();
    private TextView status;
    private FrameLayout mapContainer;
    private TextView mapPlaceholder;
    private MapView mapView;
    private Map map;
    private MapObjectManager objects;
    private final List<Image> routeMarkerImages = new ArrayList<>();
    private Image startMarkerImage;
    private Image userMarkerImage;
    private Marker userMarker;
    private ApiClient.Result route;
    private boolean routeServerBacked;
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
    private LinearLayout guidancePanel;
    private TextView guidanceLeadingIcon;
    private TextView guidanceTitle;
    private TextView guidanceSubtitle;
    private View guidanceDivider;
    private TextView guidanceTurnIcon;
    private TextView nextLabel;
    private LinearLayout pointHero;
    private LinearLayout pointList;
    private ScrollView pointListScroll;
    private LinearLayout actions;
    private TextView photoPlaceholder;
    private LinearLayout visitingNextCard;
    private TextView visitingNextIcon;
    private TextView visitingNextTitle;
    private TextView visitingNextMeta;
    private LinearLayout partnerOfferCard;
    private TextView partnerOfferView;
    private Button partnerOfferButton;
    private boolean compactScreen;
    private final List<ApiClient.PlaceOption> editingPoints = new ArrayList<>();
    private final Handler uiHandler = new Handler(Looper.getMainLooper());
    private boolean pointEditing;
    private boolean applyingPointChanges;
    private boolean resumeAfterPointEditing;
    private float dragLastY;
    private Runnable pendingPlaceSearch;
    private int searchGeneration;
    private boolean startingWalk;
    private LocationManager locationManager;
    private LocationListener locationListener;
    private LocationListener confirmationLocationListener;
    private Runnable pendingConfirmationRequest;
    private boolean positionInFlight;
    private LinearLayout zoomControls;
    private boolean routeCameraReady;
    private double routeMinLat;
    private double routeMaxLat;
    private double routeMinLon;
    private double routeMaxLon;
    private double routeCenterLat;
    private double routeCenterLon;
    private float routeZoom = 12.5f;
    private float routeMinZoom = 10.5f;
    private boolean mapInitializationStarted;
    private boolean cameraSnapshotFailureLogged;
    private int renderedRouteVersion = -1;
    private double latestUserLat = Double.NaN;
    private double latestUserLon = Double.NaN;
    private float latestUserAccuracy = Float.NaN;
    private int visitTimerBaseSeconds;
    private long visitTimerSyncedAtElapsedMillis;
    private Runnable visitTimerTick;
    private String renderedPointListKey;
    private String renderedVisitingStructureKey;
    private boolean mapGestureActive;
    private int partnerOfferRequestGeneration;
    private final Runnable cameraBoundsGuard = this::enforceRouteCameraBounds;

    @Override public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        restoredCamera = savedInstanceState != null;
        routeViewModel = new ViewModelProvider(this).get(RouteViewModel.class);
        latestUserLat = getIntent().getDoubleExtra(EXTRA_USER_LAT, Double.NaN);
        latestUserLon = getIntent().getDoubleExtra(EXTRA_USER_LON, Double.NaN);

        FrameLayout root = new FrameLayout(this);
        LinearLayout page = new LinearLayout(this);
        page.setOrientation(LinearLayout.VERTICAL);
        root.addView(page, new FrameLayout.LayoutParams(-1, -1));
        boolean compact = getResources().getConfiguration().screenHeightDp <= 720;
        compactScreen = compact;

        mapContainer = new FrameLayout(this);
        mapContainer.setBackground(UiKit.rounded(UiKit.MAP, 0, this));
        page.addView(mapContainer, new LinearLayout.LayoutParams(-1, 0, compact ? 0.47f : 0.54f));
        mapPlaceholder = UiKit.label(this,
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

        guidancePanel = new LinearLayout(this);
        guidancePanel.setOrientation(LinearLayout.HORIZONTAL);
        guidancePanel.setGravity(Gravity.CENTER_VERTICAL);
        guidancePanel.setPadding(UiKit.dp(this, 10), UiKit.dp(this, 8),
                UiKit.dp(this, 10), UiKit.dp(this, 8));
        guidancePanel.setBackground(UiKit.rounded(0xF7FFFFFF, 22, this));
        guidancePanel.setVisibility(View.GONE);
        guidanceLeadingIcon = UiKit.label(this, "🚶", 25, UiKit.GREEN_DARK);
        guidanceLeadingIcon.setGravity(Gravity.CENTER);
        guidanceLeadingIcon.setBackground(UiKit.rounded(0xFFE4F8EA, 28, this));
        guidancePanel.addView(guidanceLeadingIcon, new LinearLayout.LayoutParams(
                UiKit.dp(this, 54), UiKit.dp(this, 54)));
        LinearLayout guidanceText = new LinearLayout(this);
        guidanceText.setOrientation(LinearLayout.VERTICAL);
        guidanceText.setGravity(Gravity.CENTER_VERTICAL);
        guidanceText.setPadding(UiKit.dp(this, 12), 0, UiKit.dp(this, 8), 0);
        guidanceTitle = UiKit.label(this, "Следуйте по маршруту", 16, UiKit.TEXT);
        guidanceTitle.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        guidanceTitle.setSingleLine(true);
        guidanceTitle.setEllipsize(android.text.TextUtils.TruncateAt.END);
        guidanceSubtitle = UiKit.label(this, "До первой точки", 13, UiKit.MUTED);
        guidanceSubtitle.setSingleLine(true);
        guidanceSubtitle.setEllipsize(android.text.TextUtils.TruncateAt.END);
        guidanceText.addView(guidanceTitle);
        guidanceText.addView(guidanceSubtitle);
        guidancePanel.addView(guidanceText, new LinearLayout.LayoutParams(0, -1, 1));
        guidanceDivider = UiKit.label(this, "", 1, 0x00000000);
        guidanceDivider.setBackgroundColor(0xFFD5DAD7);
        LinearLayout.LayoutParams dividerParams = new LinearLayout.LayoutParams(
                UiKit.dp(this, 1), UiKit.dp(this, 44));
        dividerParams.rightMargin = UiKit.dp(this, 8);
        guidancePanel.addView(guidanceDivider, dividerParams);
        guidanceTurnIcon = UiKit.label(this, "↑", 34, UiKit.GREEN_DARK);
        guidanceTurnIcon.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        guidanceTurnIcon.setGravity(Gravity.CENTER);
        guidancePanel.addView(guidanceTurnIcon, new LinearLayout.LayoutParams(
                UiKit.dp(this, 48), UiKit.dp(this, 54)));
        FrameLayout.LayoutParams guidanceParams = new FrameLayout.LayoutParams(
                -1, UiKit.dp(this, 72), Gravity.BOTTOM);
        guidanceParams.setMargins(UiKit.dp(this, 10), 0, UiKit.dp(this, 10),
                UiKit.dp(this, 10));
        mapContainer.addView(guidancePanel, guidanceParams);

        zoomControls = new LinearLayout(this);
        zoomControls.setOrientation(LinearLayout.VERTICAL);
        zoomControls.setVisibility(View.GONE);
        Button zoomIn = mapControlButton("+");
        Button zoomOut = mapControlButton("−");
        zoomControls.addView(zoomIn, new LinearLayout.LayoutParams(
                UiKit.dp(this, 44), UiKit.dp(this, 44)));
        LinearLayout.LayoutParams zoomOutParams = new LinearLayout.LayoutParams(
                UiKit.dp(this, 44), UiKit.dp(this, 44));
        zoomOutParams.topMargin = UiKit.dp(this, 6);
        zoomControls.addView(zoomOut, zoomOutParams);
        FrameLayout.LayoutParams zoomParams = new FrameLayout.LayoutParams(
                -2, -2, Gravity.END | Gravity.CENTER_VERTICAL);
        zoomParams.rightMargin = UiKit.dp(this, 12);
        mapContainer.addView(zoomControls, zoomParams);
        zoomIn.setOnClickListener(view -> changeMapZoom(1f));
        zoomOut.setOnClickListener(view -> changeMapZoom(-1f));

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

        nextLabel = UiKit.label(this, "ПЕРВАЯ ТОЧКА", 12, UiKit.GREEN_DARK);
        nextLabel.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        sheet.addView(nextLabel);
        pointHero = new LinearLayout(this);
        pointHero.setGravity(Gravity.CENTER_VERTICAL);
        routeSummary = UiKit.label(this, "Загружаем маршрут…", compact ? 19 : 22, UiKit.TEXT);
        routeSummary.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        routeSummary.setMaxLines(2);
        routeSummary.setEllipsize(android.text.TextUtils.TruncateAt.END);
        pointHero.addView(routeSummary, new LinearLayout.LayoutParams(0, -2, 1));
        photoPlaceholder = UiKit.label(this, VisitingPresentation.PHOTO_PLACEHOLDER,
                11, UiKit.MUTED);
        photoPlaceholder.setGravity(Gravity.CENTER);
        photoPlaceholder.setContentDescription("Заглушка фотографии локации");
        photoPlaceholder.setBackground(UiKit.rounded(0xFFE5E9E6, 14, this));
        LinearLayout.LayoutParams photoParams = new LinearLayout.LayoutParams(
                UiKit.dp(this, compact ? 58 : 72), UiKit.dp(this, compact ? 46 : 56));
        photoParams.leftMargin = UiKit.dp(this, 12);
        pointHero.addView(photoPlaceholder, photoParams);
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

        visitingNextCard = new LinearLayout(this);
        visitingNextCard.setOrientation(LinearLayout.HORIZONTAL);
        visitingNextCard.setGravity(Gravity.CENTER_VERTICAL);
        visitingNextCard.setPadding(UiKit.dp(this, 12), UiKit.dp(this, 10),
                UiKit.dp(this, 14), UiKit.dp(this, 10));
        visitingNextCard.setBackground(UiKit.bordered(0xFFF5F8F6, 0xFFE0E9E3, 14, this));
        visitingNextIcon = UiKit.label(this, "›", 24, UiKit.GREEN_DARK);
        visitingNextIcon.setGravity(Gravity.CENTER);
        visitingNextIcon.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        visitingNextIcon.setBackground(UiKit.rounded(0xFFE3F3E8, 16, this));
        visitingNextCard.addView(visitingNextIcon, new LinearLayout.LayoutParams(
                UiKit.dp(this, 32), UiKit.dp(this, 32)));
        LinearLayout visitingNextText = new LinearLayout(this);
        visitingNextText.setOrientation(LinearLayout.VERTICAL);
        visitingNextTitle = UiKit.label(this, "", compact ? 14 : 15, UiKit.TEXT);
        visitingNextTitle.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        visitingNextTitle.setSingleLine(true);
        visitingNextTitle.setEllipsize(android.text.TextUtils.TruncateAt.END);
        visitingNextMeta = UiKit.label(this, "", 12, UiKit.MUTED);
        visitingNextMeta.setSingleLine(true);
        visitingNextMeta.setEllipsize(android.text.TextUtils.TruncateAt.END);
        visitingNextText.addView(visitingNextTitle);
        visitingNextText.addView(visitingNextMeta);
        LinearLayout.LayoutParams nextTextParams = new LinearLayout.LayoutParams(0, -2, 1);
        nextTextParams.leftMargin = UiKit.dp(this, 10);
        visitingNextCard.addView(visitingNextText, nextTextParams);
        visitingNextCard.setVisibility(View.GONE);
        LinearLayout.LayoutParams nextCardParams = new LinearLayout.LayoutParams(-1, -2);
        nextCardParams.topMargin = UiKit.dp(this, 2);
        nextCardParams.bottomMargin = UiKit.dp(this, 6);
        sheet.addView(visitingNextCard, nextCardParams);

        partnerOfferCard = new LinearLayout(this);
        partnerOfferCard.setOrientation(LinearLayout.VERTICAL);
        partnerOfferCard.setPadding(UiKit.dp(this, 14), UiKit.dp(this, 11),
                UiKit.dp(this, 14), UiKit.dp(this, 11));
        partnerOfferCard.setBackground(UiKit.rounded(0xFFFFF6DF, 14, this));
        TextView partnerDisclosure = UiKit.label(
                this, "ПАРТНЁРСКОЕ ПРЕДЛОЖЕНИЕ", 11, UiKit.RED_SOFT);
        partnerDisclosure.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        partnerOfferCard.addView(partnerDisclosure);
        partnerOfferView = UiKit.label(this, "", 13, UiKit.TEXT);
        partnerOfferView.setPadding(0, UiKit.dp(this, 5), 0, UiKit.dp(this, 7));
        partnerOfferCard.addView(partnerOfferView);
        partnerOfferButton = UiKit.button(
                this, "Открыть в 2ГИС", UiKit.GREEN_DARK, 0xFFFFFFFF);
        partnerOfferButton.setOnClickListener(view -> openPartnerOffer());
        partnerOfferCard.addView(partnerOfferButton, new LinearLayout.LayoutParams(-1, -2));
        partnerOfferCard.setVisibility(View.GONE);
        sheet.addView(partnerOfferCard, new LinearLayout.LayoutParams(-1, -2));

        pointList = new LinearLayout(this);
        pointList.setOrientation(LinearLayout.VERTICAL);
        pointListScroll = new ScrollView(this);
        pointListScroll.setFillViewport(true);
        pointListScroll.setVerticalScrollBarEnabled(true);
        pointListScroll.setScrollbarFadingEnabled(false);
        pointListScroll.setOverScrollMode(View.OVER_SCROLL_IF_CONTENT_SCROLLS);
        pointListScroll.addView(pointList, new ScrollView.LayoutParams(-1, -2));
        sheet.addView(pointListScroll, new LinearLayout.LayoutParams(-1, 0, 1));

        actions = new LinearLayout(this);
        actions.setOrientation(LinearLayout.HORIZONTAL);
        actions.setGravity(Gravity.CENTER_VERTICAL);
        actions.setBaselineAligned(false);
        editQuery = compactAction("Изменить маршрут");
        editPoints = compactAction("Редактировать точки");
        primaryAction = UiKit.button(this, "▶", UiKit.GREEN, 0xFFFFFFFF);
        primaryAction.setTextSize(22);
        primaryAction.setMinWidth(0);
        primaryAction.setMinHeight(0);
        primaryAction.setElevation(0f);
        primaryAction.setStateListAnimator(null);
        primaryAction.setPadding(0, 0, 0, 0);
        LinearLayout.LayoutParams editActionParams = new LinearLayout.LayoutParams(0,
                UiKit.dp(this, compact ? 48 : 54), 1);
        editActionParams.rightMargin = UiKit.dp(this, 7);
        actions.addView(editQuery, editActionParams);
        LinearLayout.LayoutParams pointsActionParams = new LinearLayout.LayoutParams(0,
                UiKit.dp(this, compact ? 48 : 54), 1.12f);
        pointsActionParams.rightMargin = UiKit.dp(this, 7);
        actions.addView(editPoints, pointsActionParams);
        actions.addView(primaryAction, new LinearLayout.LayoutParams(
                UiKit.dp(this, compact ? 52 : 58), UiKit.dp(this, compact ? 48 : 54)));
        LinearLayout.LayoutParams actionsParams = new LinearLayout.LayoutParams(
                -1, UiKit.dp(this, compact ? 52 : 58));
        actionsParams.topMargin = UiKit.dp(this, 4);
        sheet.addView(actions, actionsParams);
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

        close.setOnClickListener(view -> {
            if (pointEditing) cancelPointEditing();
            else returnToMain();
        });
        editQuery.setOnClickListener(view -> openRouteChat());
        editPoints.setOnClickListener(view -> {
            if (pointEditing) applyPointChangesInline();
            else enterPointEditing();
        });
        primaryAction.setOnClickListener(view -> {
            if (walk != null && walk.success && ("ACTIVE".equals(walk.status)
                    || "PAUSED".equals(walk.status))) showWalkMenu();
            else startWalk();
        });
        pauseResume.setOnClickListener(view -> {
            if (walk != null && walk.success) {
                sendWalkAction("PAUSED".equals(walk.status) ? "RESUME" : "PAUSE");
            }
        });

        openRouteFromIntent();
    }

    @Override public void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        // MapActivity can be reused by Android. A cached result is valid only
        // for the exact route that created it; otherwise a history preview can
        // be shown instead of the newly generated route.
        route = null;
        walk = null;
        routeViewModel.route = null;
        routeViewModel.walk = null;
        openRouteFromIntent();
    }

    private void openRouteFromIntent() {
        String requestedRouteId = getIntent().getStringExtra(EXTRA_ROUTE_ID);
        int requestedRouteVersion = getIntent().getIntExtra(EXTRA_ROUTE_VERSION, 0);
        boolean walkMode = getIntent().getStringExtra(EXTRA_WALK_ID) != null;
        route = routeViewModel.route;
        walk = routeViewModel.walk;
        boolean cachedRouteMatches = route != null && requestedRouteId != null
                && requestedRouteId.equals(route.routeId)
                && (requestedRouteVersion < 1 || requestedRouteVersion == route.routeVersion);
        if (!cachedRouteMatches) {
            // ViewModel survives a recreation. Never let that survival cross
            // a route boundary.
            route = null;
            walk = null;
            routeViewModel.route = null;
            routeViewModel.walk = null;
            loadRoute();
            return;
        }
        showRouteStatus();
        initializeMapIfReady();
        if (walkMode) {
            if (walk == null) loadWalk(); else showWalkStatus();
        }
    }

    private void openRouteChat() {
        if (isReadOnlyView() || route == null || route.routeId == null) return;
        Intent chat = new Intent(this, RouteChatActivity.class);
        chat.putExtra(RouteChatActivity.EXTRA_CITY, routeCityId());
        chat.putExtra(RouteChatActivity.EXTRA_SESSION, getIntent().getStringExtra(EXTRA_SESSION_ID));
        chat.putExtra(RouteChatActivity.EXTRA_ROUTE_ID, route.routeId);
        chat.putExtra(RouteChatActivity.EXTRA_ROUTE_VERSION, route.routeVersion);
        startActivityForResult(chat, ROUTE_CHAT_REQUEST);
    }

    private String routeCityId() { return getIntent().getStringExtra(EXTRA_CITY_ID); }

    @Override protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != ROUTE_CHAT_REQUEST || resultCode != RESULT_OK || data == null) return;
        String newRouteId = data.getStringExtra(RouteChatActivity.EXTRA_ROUTE_ID);
        if (newRouteId == null || !newRouteId.equals(getIntent().getStringExtra(EXTRA_ROUTE_ID))) return;
        getIntent().putExtra(EXTRA_ROUTE_SNAPSHOT, data.getStringExtra(RouteChatActivity.EXTRA_SNAPSHOT));
        getIntent().putExtra(EXTRA_ROUTE_ID, newRouteId);
        getIntent().putExtra(EXTRA_ROUTE_VERSION,
                data.getIntExtra(RouteChatActivity.EXTRA_ROUTE_VERSION, 0));
        loadRoute();
    }

    private Button compactAction(String text) {
        Button button = UiKit.button(this, text, 0xFFFFFFFF, UiKit.GREEN_DARK);
        button.setTextSize(12);
        button.setSingleLine(true);
        button.setPadding(UiKit.dp(this, 3), 0, UiKit.dp(this, 3), 0);
        button.setMinWidth(0);
        button.setMinHeight(0);
        button.setElevation(0f);
        button.setStateListAnimator(null);
        button.setBackground(UiKit.bordered(0xFFFFFFFF, UiKit.GREEN, 14, this));
        return button;
    }

    private Button mapControlButton(String text) {
        Button button = UiKit.button(this, text, 0xF2FFFFFF, UiKit.TEXT);
        button.setTextSize(24);
        button.setMinWidth(0);
        button.setMinHeight(0);
        button.setPadding(0, 0, 0, 0);
        button.setElevation(UiKit.dp(this, 2));
        return button;
    }

    private void initializeMapIfReady() {
        if (mapInitializationStarted || mapView != null || map != null
                || route == null || !route.success || isFinishing() || isDestroyed()) return;
        mapInitializationStarted = true;
        logMemory("before-sdk");
        if (hasCriticalMemoryPressure()) {
            showMapFallback("Недостаточно свободной памяти для карты 2ГИС\n"
                    + "Маршрут и точки доступны без неё");
            Log.w(MEMORY_LOG, "Map initialization skipped: Android reports low memory");
            return;
        }

        GulyayApplication application = (GulyayApplication) getApplication();
        try {
            ru.dgis.sdk.Context sdkContext = application.sdkContext();
            if (sdkContext == null) {
                String message = application.mapError();
                showMapFallback(message == null
                        ? "Карта 2ГИС пока недоступна\nМаршрут и точки работают без неё"
                        : message);
                return;
            }
            logMemory("after-sdk");
            double[] center = cityCenter(getIntent().getStringExtra(EXTRA_CITY_ID));
            MapOptions options = new MapOptions();
            options.setPosition(camera(center[0], center[1], 12.5f));
            mapView = new MapView(this, options);
            mapView.setId(R.id.route_map_view);
            mapView.setClickable(true);
            mapView.setFocusable(true);
            getLifecycle().addObserver(mapView);
            mapContainer.addView(mapView, 0, new FrameLayout.LayoutParams(-1, -1));
            mapContainer.removeView(mapPlaceholder);
            zoomControls.setVisibility(View.VISIBLE);
            logMemory("after-map-view");
            final MapView requestedMapView = mapView;
            requestedMapView.getMapAsync(readyMap -> {
                if (!MapLifecycleGuard.shouldApplyMapCallback(requestedMapView, mapView,
                        mapInitializationStarted, !isFinishing() && !isDestroyed())) {
                    Log.i(MEMORY_LOG, "Ignoring callback from released MapView");
                    return Unit.INSTANCE;
                }
                try {
                    map = readyMap;
                    renderRoute();
                    logMemory("map-ready");
                } catch (RuntimeException | LinkageError error) {
                    Log.e(MEMORY_LOG, "2GIS route rendering failed", error);
                    showMapFallback("Не удалось отрисовать карту 2ГИС\n"
                            + "Маршрут и точки сохранены");
                } catch (OutOfMemoryError error) {
                    Log.e(MEMORY_LOG, "Not enough memory to render route markers", error);
                    showMapFallback("Эмулятору не хватило памяти для карты 2ГИС\n"
                            + "Маршрут и точки сохранены");
                }
                return Unit.INSTANCE;
            });
        } catch (RuntimeException | LinkageError error) {
            Log.e(MEMORY_LOG, "2GIS map initialization failed", error);
            showMapFallback("Не удалось открыть карту 2ГИС\nМаршрут и точки доступны без неё");
        } catch (OutOfMemoryError error) {
            Log.e(MEMORY_LOG, "Not enough memory to create 2GIS MapView", error);
            showMapFallback("Эмулятору не хватило памяти для карты 2ГИС\n"
                    + "Маршрут и точки доступны без неё");
        }
    }

    private void showMapFallback(String message) {
        mapInitializationStarted = false;
        releaseMapResources();
        if (mapView != null) {
            getLifecycle().removeObserver(mapView);
            mapContainer.removeView(mapView);
            mapView = null;
        }
        zoomControls.setVisibility(View.GONE);
        mapPlaceholder.setText(message + "\nНажмите, чтобы повторить");
        mapPlaceholder.setOnClickListener(view -> {
            if (route == null || !route.success || mapInitializationStarted) return;
            mapPlaceholder.setText("Проверяем доступную память и запускаем карту…");
            initializeMapIfReady();
        });
        if (mapPlaceholder.getParent() == null) {
            mapContainer.addView(mapPlaceholder, 0, new FrameLayout.LayoutParams(-1, -1));
        }
    }

    private boolean hasCriticalMemoryPressure() {
        ActivityManager manager = (ActivityManager) getSystemService(Context.ACTIVITY_SERVICE);
        if (manager == null) return false;
        ActivityManager.MemoryInfo info = new ActivityManager.MemoryInfo();
        manager.getMemoryInfo(info);
        return info.lowMemory;
    }

    private void logMemory(String stage) {
        ActivityManager manager = (ActivityManager) getSystemService(Context.ACTIVITY_SERVICE);
        ActivityManager.MemoryInfo info = new ActivityManager.MemoryInfo();
        if (manager != null) manager.getMemoryInfo(info);
        Runtime runtime = Runtime.getRuntime();
        long javaUsed = runtime.totalMemory() - runtime.freeMemory();
        Log.i(MEMORY_LOG, stage
                + " javaMb=" + javaUsed / 1_048_576L
                + " nativeMb=" + Debug.getNativeHeapAllocatedSize() / 1_048_576L
                + " availableMb=" + info.availMem / 1_048_576L
                + " lowMemory=" + info.lowMemory);
    }

    private void loadRoute() {
        String routeId = getIntent().getStringExtra(EXTRA_ROUTE_ID);
        String cityId = getIntent().getStringExtra(EXTRA_CITY_ID);
        String sessionId = getIntent().getStringExtra(EXTRA_SESSION_ID);
        int expectedVersion = getIntent().getIntExtra(EXTRA_ROUTE_VERSION, 0);
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
                if (isFinishing() || isDestroyed()
                        || !routeId.equals(getIntent().getStringExtra(EXTRA_ROUTE_ID))
                        || expectedVersion != getIntent().getIntExtra(EXTRA_ROUTE_VERSION, 0)) return;
                int previousRenderedRouteVersion = renderedRouteVersion;
                route = finalResponse;
                if (!route.success) {
                    // A snapshot can help the user view a route during a
                    // transient outage, but must never mask an ownership/404
                    // failure or be used as a startable backend route.
                    if ("NOT_FOUND".equals(route.errorCode)
                            || "UNAUTHORIZED".equals(route.errorCode)
                            || "VERSION_CONFLICT".equals(route.errorCode)) {
                        status.setText(route.message);
                        primaryAction.setEnabled(false);
                        return;
                    }
                    String snapshot = getIntent().getStringExtra(EXTRA_ROUTE_SNAPSHOT);
                    ApiClient.Result saved = ApiClient.routeFromSnapshot(snapshot);
                    if (!ApiClient.isSnapshotValidForOfflineView(snapshot, routeId, expectedVersion,
                            SystemClock.elapsedRealtime())) {
                        status.setText("Срок хранения гостевого маршрута истёк. Создайте новый маршрут.");
                        return;
                    }
                    if (saved == null) {
                        status.setText(route.message);
                        return;
                    }
                    route = saved;
                    routeServerBacked = false;
                    status.setText("Нет соединения. Открыта сохранённая версия маршрута. "
                            + "Просмотр точек доступен, управление прогулкой — после подключения.");
                } else {
                    routeServerBacked = true;
                }
                routeViewModel.route = route;
                showRouteStatus();
                // A chat revision keeps routeId but increments routeVersion.
                // The existing MapView must therefore be redrawn explicitly:
                // otherwise its old polyline and markers stay on screen.
                boolean revisedRoute = route.success
                        && route.routeVersion != previousRenderedRouteVersion;
                if (map != null && revisedRoute) {
                    renderRoute(true);
                } else {
                    initializeMapIfReady();
                }
                // The home-screen play button creates the walk first and then
                // opens this activity with EXTRA_WALK_ID. Route loading is
                // asynchronous, so continue by loading that walk once the
                // route is ready; otherwise the map incorrectly stays in the
                // READY state while the backend already reports ACTIVE.
                if (!routeServerBacked) {
                    return;
                }
                if (getIntent().getStringExtra(EXTRA_WALK_ID) != null) {
                    loadWalk();
                } else {
                    syncLocationTracking();
                }
            });
        });
    }

    private void showRouteStatus() {
        if (route == null || !route.success) return;
        resetVisitingUi();
        if (isOfflineView()) {
            String lastKnownStatus = lastKnownStatusLabel();
            screenTitle.setText("Сохранённый маршрут");
            routeSummary.setText(route.points.isEmpty() ? "Маршрут" : route.points.get(0).name);
            status.setText("Нет соединения. Открыта сохранённая версия маршрута. "
                    + "Последний статус: " + lastKnownStatus + " (не подтверждён сервером).");
            guidancePanel.setVisibility(View.GONE);
            mapRouteSummary.setVisibility(View.VISIBLE);
            mapRouteSummary.setText("Офлайн-просмотр • " + route.points.size() + " мест");
            primaryAction.setVisibility(View.GONE);
            editQuery.setVisibility(View.GONE);
            editPoints.setVisibility(View.GONE);
            pauseResume.setVisibility(View.GONE);
            stopWalk.setVisibility(View.GONE);
            renderPointList(0);
            return;
        }
        if (getIntent().getBooleanExtra(EXTRA_HISTORY_READ_ONLY, false)) {
            String historyStatus = getIntent().getStringExtra(EXTRA_WALK_STATUS);
            String statusLabel = lastKnownStatusLabel();
            screenTitle.setText("Маршрут из истории");
            routeSummary.setText(route.points.isEmpty() ? "Маршрут" : route.points.get(0).name);
            status.setText("Просмотр истории • " + statusLabel + " • "
                    + route.points.size() + " мест");
            guidancePanel.setVisibility(View.GONE);
            mapRouteSummary.setVisibility(View.VISIBLE);
            mapRouteSummary.setText(statusLabel);
            primaryAction.setVisibility(View.GONE);
            editQuery.setVisibility(View.GONE);
            editPoints.setVisibility(View.GONE);
            pauseResume.setVisibility(View.GONE);
            stopWalk.setVisibility(View.GONE);
            renderPointList(0);
            return;
        }
        if (walk != null && walk.success) {
            showWalkStatus();
            return;
        }
        screenTitle.setText("Прогулка по " + cityName() + "\nМаршрут построен");
        routeSummary.setText(route.points.isEmpty() ? "Маршрут" : route.points.get(0).name);
        String time = route.totalMinutes > 0 ? route.totalMinutes + " мин" : "время рассчитано";
        String distance = route.totalDistanceMeters > 0
                ? String.format(java.util.Locale.US, " • %.1f км", route.totalDistanceMeters / 1000.0)
                : "";
        status.setText("◷  " + time + "                   ●  " + route.points.size() + " места");
        guidancePanel.setVisibility(View.GONE);
        mapRouteSummary.setVisibility(View.VISIBLE);
        mapRouteSummary.setText("🚶  Маршрут готов\n" + route.points.size() + " места • "
                + time + distance);
        primaryAction.setText("▶");
        primaryAction.setTextColor(0xFFFFFFFF);
        primaryAction.setBackground(UiKit.rounded(UiKit.GREEN, 14, this));
        editQuery.setEnabled(true);
        editPoints.setEnabled(true);
        renderPointList(0);
    }

    private String lastKnownStatusLabel() {
        if (getIntent().getBooleanExtra(EXTRA_WALK_STATUS_UNCONFIRMED, false)) {
            return "неизвестен";
        }
        return RouteLifecycleRecovery.historyStatusLabel(
                getIntent().getStringExtra(EXTRA_WALK_STATUS));
    }

    @Override public boolean dispatchTouchEvent(MotionEvent event) {
        int action = event.getActionMasked();
        if (action == MotionEvent.ACTION_DOWN) {
            mapGestureActive = isTouchInside(mapContainer, event);
            if (mapGestureActive) uiHandler.removeCallbacks(cameraBoundsGuard);
        }
        boolean handled = super.dispatchTouchEvent(event);
        if (routeCameraReady && mapGestureActive && (action == MotionEvent.ACTION_UP
                || action == MotionEvent.ACTION_CANCEL)) {
            uiHandler.removeCallbacks(cameraBoundsGuard);
            uiHandler.postDelayed(cameraBoundsGuard, 40L);
            uiHandler.postDelayed(cameraBoundsGuard, 260L);
            uiHandler.postDelayed(cameraBoundsGuard, 900L);
        }
        if (action == MotionEvent.ACTION_UP || action == MotionEvent.ACTION_CANCEL) {
            mapGestureActive = false;
        }
        return handled;
    }

    private boolean isTouchInside(View view, MotionEvent event) {
        if (view == null || view.getVisibility() != View.VISIBLE) return false;
        int[] location = new int[2];
        view.getLocationOnScreen(location);
        float x = event.getRawX();
        float y = event.getRawY();
        return x >= location[0] && x < location[0] + view.getWidth()
                && y >= location[1] && y < location[1] + view.getHeight();
    }

    private String cityName() {
        String cityId = getIntent().getStringExtra(EXTRA_CITY_ID);
        if ("moscow".equals(cityId)) return "Москве";
        if ("vladimir".equals(cityId)) return "Владимиру";
        if ("borovsk".equals(cityId)) return "Боровску";
        return "Туле";
    }

    private void renderPointList(int currentOrder) {
        renderPointList(currentOrder, false);
    }

    private void renderPointList(int currentOrder, boolean nextPointAlreadyFeatured) {
        String renderKey = VisitingPresentation.pointListRenderKey(
                route, currentOrder, nextPointAlreadyFeatured);
        if (renderKey.equals(renderedPointListKey)) return;
        renderedPointListKey = renderKey;
        pointList.removeAllViews();
        if (route == null || route.points.isEmpty()) return;
        int start = currentOrder > 0 ? currentOrder : 1;
        if (nextPointAlreadyFeatured) start++;
        int end = route.points.size();
        for (int i = start; i < end; i++) {
            ApiClient.PlaceOption point = route.points.get(i);
            LinearLayout row = new LinearLayout(this);
            row.setGravity(Gravity.CENTER_VERTICAL);
            row.setPadding(0, UiKit.dp(this, 4), UiKit.dp(this, 5), UiKit.dp(this, 4));
            TextView number = UiKit.label(this, String.valueOf(i + 1), 14, 0xFFFFFFFF);
            number.setGravity(Gravity.CENTER);
            number.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
            number.setBackground(UiKit.rounded(0xFFE9F8EE, 20, this));
            number.setTextColor(UiKit.GREEN_DARK);
            row.addView(number, new LinearLayout.LayoutParams(
                    UiKit.dp(this, 32), UiKit.dp(this, 32)));
            String suffix = point.food ? " • заведение" : "";
            TextView name = UiKit.label(this, point.name + suffix + "\n" + travelToPoint(i), 13, UiKit.TEXT);
            name.setMaxLines(2);
            name.setEllipsize(android.text.TextUtils.TruncateAt.END);
            name.setPadding(UiKit.dp(this, 12), 0, UiKit.dp(this, 8), 0);
            row.addView(name, new LinearLayout.LayoutParams(0, -2, 1));
            pointList.addView(row, new LinearLayout.LayoutParams(
                    -1, UiKit.dp(this, 54)));
        }
        if (walk != null && "VISITING".equals(walk.phase)) {
            pointListScroll.setVisibility(pointList.getChildCount() > 0
                    ? View.VISIBLE : View.GONE);
        }
        pointListScroll.post(() -> pointListScroll.scrollTo(0, 0));
    }

    private String travelToPoint(int pointIndex) {
        ApiClient.PlaceOption target = route.points.get(pointIndex);
        double lat = pointIndex == 0 ? routeStartLat() : route.points.get(pointIndex - 1).lat;
        double lon = pointIndex == 0 ? routeStartLon() : route.points.get(pointIndex - 1).lon;
        int meters = (int) Math.round(meters(lat, lon, target.lat, target.lon));
        int minutes = Math.max(1, (int) Math.ceil(meters / 75.0));
        return (meters >= 1000 ? String.format(java.util.Locale.US, "%.1f км", meters / 1000.0)
                : meters + " м") + " • " + minutes + " мин пешком";
    }

    private void enterPointEditing() {
        if (isReadOnlyView() || route == null || !route.success || applyingPointChanges) return;
        if (walk != null && walk.success && "ACTIVE".equals(walk.status)) {
            pauseWalkForPointEditing();
            return;
        }
        resumeAfterPointEditing = false;
        beginPointEditingUi();
    }

    private void pauseWalkForPointEditing() {
        if (isReadOnlyView()) return;
        applyingPointChanges = true;
        editPoints.setEnabled(false);
        status.setText("Ставим прогулку на паузу для редактирования…");
        String sessionId = getIntent().getStringExtra(EXTRA_SESSION_ID);
        network.execute(() -> {
            ApiClient.WalkResult response;
            try {
                response = ApiClient.walkAction(walk.walkId, sessionId, "PAUSE");
            } catch (Exception error) {
                response = new ApiClient.WalkResult(false,
                        "Не удалось поставить прогулку на паузу.", walk.walkId,
                        walk.status, walk.currentPointOrder, walk.remainingMinutes,
                        false, -1, null);
            }
            ApiClient.WalkResult finalResponse = response;
            runOnUiThread(() -> {
                applyingPointChanges = false;
                if (isFinishing() || isDestroyed()) return;
                editPoints.setEnabled(true);
                if (!finalResponse.success || !"PAUSED".equals(finalResponse.status)) {
                    status.setText(finalResponse.message);
                    return;
                }
                walk = finalResponse;
                routeViewModel.walk = walk;
                resumeAfterPointEditing = true;
                beginPointEditingUi();
            });
        });
    }

    private void beginPointEditingUi() {
        editingPoints.clear();
        editingPoints.addAll(route.points);
        pointEditing = true;
        guidancePanel.setVisibility(View.GONE);
        mapRouteSummary.setVisibility(View.VISIBLE);
        screenTitle.setText("Редактирование маршрута");
        mapRouteSummary.setText("Меняйте порядок прямо здесь\nЗажмите ≡ и перетащите точку");
        nextLabel.setText("ТОЧКИ МАРШРУТА");
        pointHero.setVisibility(View.GONE);
        status.setVisibility(View.GONE);
        visitingNextCard.setVisibility(View.GONE);
        invalidatePartnerOffer();
        editQuery.setVisibility(View.GONE);
        primaryAction.setVisibility(View.GONE);
        editPoints.setText("Подтвердить");
        renderEditablePointList();
    }

    private void cancelPointEditing() {
        if (!pointEditing || applyingPointChanges) return;
        editingPoints.clear();
        pointEditing = false;
        restoreRouteLayout();
        finishPointEditing();
    }

    private void finishPointEditing() {
        if (!resumeAfterPointEditing) {
            showRouteStatus();
            return;
        }
        resumeAfterPointEditing = false;
        applyingPointChanges = true;
        editPoints.setEnabled(false);
        status.setText("Возобновляем прогулку…");
        String sessionId = getIntent().getStringExtra(EXTRA_SESSION_ID);
        network.execute(() -> {
            ApiClient.WalkResult response;
            try {
                response = ApiClient.walkAction(walk.walkId, sessionId, "RESUME");
            } catch (Exception error) {
                response = new ApiClient.WalkResult(false,
                        "Маршрут сохранён, но прогулка осталась на паузе.", walk.walkId,
                        walk.status, walk.currentPointOrder, walk.remainingMinutes,
                        false, -1, null);
            }
            ApiClient.WalkResult finalResponse = response;
            runOnUiThread(() -> {
                applyingPointChanges = false;
                if (isFinishing() || isDestroyed()) return;
                editPoints.setEnabled(true);
                if (finalResponse.success) {
                    walk = finalResponse;
                    routeViewModel.walk = walk;
                    showWalkStatus();
                    syncLocationTracking();
                } else {
                    showWalkStatus();
                    status.setText(finalResponse.message);
                }
            });
        });
    }

    private void restoreRouteLayout() {
        nextLabel.setText("ПЕРВАЯ ТОЧКА");
        pointHero.setVisibility(View.VISIBLE);
        status.setVisibility(View.VISIBLE);
        editQuery.setVisibility(View.VISIBLE);
        primaryAction.setVisibility(View.VISIBLE);
        editPoints.setText("Редактировать точки");
        editPoints.setEnabled(true);
    }

    private void renderEditablePointList() {
        renderedPointListKey = null;
        pointList.removeAllViews();
        for (int i = 0; i < editingPoints.size(); i++) {
            LinearLayout row = editablePointRow(editingPoints.get(i), i);
            pointList.addView(row, new LinearLayout.LayoutParams(
                    -1, UiKit.dp(this, 54)));
        }
        Button add = new Button(this);
        add.setText("＋  Добавить точку");
        add.setTextSize(15);
        add.setTextColor(UiKit.GREEN_DARK);
        add.setAllCaps(false);
        add.setGravity(Gravity.CENTER_VERTICAL | Gravity.START);
        add.setPadding(UiKit.dp(this, 8), 0, UiKit.dp(this, 8), 0);
        add.setBackgroundColor(0x00000000);
        add.setOnClickListener(view -> showPlaceSearch());
        pointList.addView(add, new LinearLayout.LayoutParams(
                -1, UiKit.dp(this, 52)));
    }

    private LinearLayout editablePointRow(ApiClient.PlaceOption point, int index) {
        LinearLayout row = new LinearLayout(this);
        row.setTag(index);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.setBackground(UiKit.bordered(0xFFFFFFFF, 0xFFE6EBE7, 12, this));
        row.setPadding(UiKit.dp(this, 8), 0, UiKit.dp(this, 4), 0);

        TextView number = UiKit.label(this, String.valueOf(index + 1), 13, UiKit.GREEN_DARK);
        number.setGravity(Gravity.CENTER);
        number.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        number.setBackground(UiKit.rounded(0xFFE9F8EE, 18, this));
        row.addView(number, new LinearLayout.LayoutParams(
                UiKit.dp(this, 32), UiKit.dp(this, 32)));

        TextView name = UiKit.label(this, point.name, 14, UiKit.TEXT);
        name.setMaxLines(2);
        name.setEllipsize(android.text.TextUtils.TruncateAt.END);
        name.setPadding(UiKit.dp(this, 10), 0, UiKit.dp(this, 4), 0);
        row.addView(name, new LinearLayout.LayoutParams(0, -2, 1));

        Button remove = new Button(this);
        remove.setText("×");
        remove.setTextSize(23);
        remove.setTextColor(UiKit.MUTED);
        remove.setMinWidth(0);
        remove.setMinHeight(0);
        remove.setPadding(0, 0, 0, 0);
        remove.setBackgroundColor(0x00000000);
        remove.setOnClickListener(view -> removeEditablePoint(row));
        row.addView(remove, new LinearLayout.LayoutParams(
                UiKit.dp(this, 42), UiKit.dp(this, 48)));

        TextView drag = UiKit.label(this, "≡", 28, UiKit.MUTED);
        drag.setGravity(Gravity.CENTER);
        drag.setOnTouchListener((view, event) -> handlePointDrag(row, event));
        row.addView(drag, new LinearLayout.LayoutParams(
                UiKit.dp(this, 40), UiKit.dp(this, 50)));
        return row;
    }

    private void removeEditablePoint(LinearLayout row) {
        if (editingPoints.size() <= 1) {
            Toast.makeText(this, "В маршруте должна остаться хотя бы одна точка.",
                    Toast.LENGTH_SHORT).show();
            return;
        }
        int index = (Integer) row.getTag();
        if (index < 0 || index >= editingPoints.size()) return;
        editingPoints.remove(index);
        renderEditablePointList();
    }

    private boolean handlePointDrag(LinearLayout row, MotionEvent event) {
        if (!pointEditing || applyingPointChanges) return false;
        if (event.getActionMasked() == MotionEvent.ACTION_DOWN) {
            dragLastY = event.getRawY();
            row.setAlpha(0.72f);
            pointListScroll.requestDisallowInterceptTouchEvent(true);
            return true;
        }
        if (event.getActionMasked() == MotionEvent.ACTION_MOVE) {
            float delta = event.getRawY() - dragLastY;
            if (Math.abs(delta) < UiKit.dp(this, 30)) return true;
            int index = (Integer) row.getTag();
            int target = index + (delta > 0 ? 1 : -1);
            if (target >= 0 && target < editingPoints.size()) {
                Collections.swap(editingPoints, index, target);
                pointList.removeView(row);
                pointList.addView(row, target);
                refreshEditableRowPositions();
                dragLastY = event.getRawY();
            }
            return true;
        }
        if (event.getActionMasked() == MotionEvent.ACTION_UP
                || event.getActionMasked() == MotionEvent.ACTION_CANCEL) {
            row.setAlpha(1f);
            pointListScroll.requestDisallowInterceptTouchEvent(false);
            return true;
        }
        return true;
    }

    private void refreshEditableRowPositions() {
        for (int i = 0; i < editingPoints.size(); i++) {
            View child = pointList.getChildAt(i);
            if (!(child instanceof LinearLayout)) continue;
            LinearLayout row = (LinearLayout) child;
            row.setTag(i);
            View number = row.getChildAt(0);
            if (number instanceof TextView) ((TextView) number).setText(String.valueOf(i + 1));
        }
    }

    private void applyPointChangesInline() {
        applyPointChangesInline(false);
    }

    private void applyPointChangesInline(boolean allowDurationOverrun) {
        if (isReadOnlyView()) return;
        if (!pointEditing || applyingPointChanges || route == null || editingPoints.isEmpty()) return;
        applyingPointChanges = true;
        editPoints.setEnabled(false);
        editPoints.setText("Пересчитываем…");
        mapRouteSummary.setText("Проверяем точки и пересчитываем переходы…");
        List<ApiClient.PlaceOption> requested = new ArrayList<>(editingPoints);
        String routeId = getIntent().getStringExtra(EXTRA_ROUTE_ID);
        String cityId = getIntent().getStringExtra(EXTRA_CITY_ID);
        String sessionId = getIntent().getStringExtra(EXTRA_SESSION_ID);
        int baseVersion = route.routeVersion;
        network.execute(() -> {
            ApiClient.Result response;
            boolean refreshedAfterConflict = false;
            try {
                response = ApiClient.revisePoints(routeId, baseVersion, cityId,
                        requested, sessionId, allowDurationOverrun);
                if (!response.success && "VERSION_CONFLICT".equals(response.errorCode)) {
                    response = ApiClient.getRoute(routeId, cityId, sessionId);
                    refreshedAfterConflict = response.success;
                }
            } catch (Exception error) {
                response = new ApiClient.Result(false,
                        "Не удалось сохранить точки. Исходный маршрут не изменён.", null, 0);
            }
            ApiClient.Result finalResponse = response;
            boolean finalRefreshedAfterConflict = refreshedAfterConflict;
            runOnUiThread(() -> {
                applyingPointChanges = false;
                if (isFinishing() || isDestroyed()) return;
                if (!finalResponse.success) {
                    editPoints.setEnabled(true);
                    editPoints.setText("Подтвердить");
                    if ("TIME_BUDGET_CONFIRMATION_REQUIRED".equals(finalResponse.errorCode)) {
                        showDurationOverrunConfirmation(finalResponse);
                        return;
                    }
                    mapRouteSummary.setText(finalResponse.message);
                    return;
                }
                route = finalResponse;
                routeViewModel.route = route;
                if (finalRefreshedAfterConflict) {
                    editingPoints.clear();
                    editingPoints.addAll(route.points);
                    editPoints.setEnabled(true);
                    editPoints.setText("Подтвердить");
                    mapRouteSummary.setText("Маршрут уже изменился\nАктуальные точки загружены — повторите правки");
                    renderEditablePointList();
                    renderRoute();
                    return;
                }
                editingPoints.clear();
                pointEditing = false;
                restoreRouteLayout();
                renderRoute();
                finishPointEditing();
            });
        });
    }

    private void showDurationOverrunConfirmation(ApiClient.Result response) {
        String message = "После изменения маршрут займёт около "
                + formatDuration(response.projectedMinutes) + " — на "
                + response.overrunMinutes + " мин. больше выбранных вами "
                + formatDuration(response.requestedMinutes) + ". Всё равно применить?";
        new AlertDialog.Builder(this)
                .setMessage(message)
                .setNegativeButton("Отмена", null)
                .setPositiveButton("Всё равно применить",
                        (dialog, which) -> applyPointChangesInline(true))
                .show();
    }

    private static String formatDuration(int minutes) {
        if (minutes < 0) return "неизвестное время";
        int hours = minutes / 60;
        int rest = minutes % 60;
        if (hours == 0) return minutes + " мин.";
        return rest == 0 ? hours + " ч." : hours + " ч " + rest + " мин.";
    }

    private void showPlaceSearch() {
        if (!pointEditing || applyingPointChanges) return;
        if (editingPoints.size() >= 8) {
            Toast.makeText(this, "В маршруте может быть не больше восьми точек.",
                    Toast.LENGTH_SHORT).show();
            return;
        }
        Dialog dialog = new Dialog(this);
        dialog.requestWindowFeature(Window.FEATURE_NO_TITLE);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(UiKit.dp(this, 18), UiKit.dp(this, 18),
                UiKit.dp(this, 18), UiKit.dp(this, 18));
        root.setBackgroundColor(0xFFFFFFFF);

        LinearLayout header = new LinearLayout(this);
        header.setGravity(Gravity.CENTER_VERTICAL);
        Button back = new Button(this);
        back.setText("‹");
        back.setTextSize(30);
        back.setTextColor(UiKit.TEXT);
        back.setPadding(0, 0, 0, 0);
        back.setMinWidth(0);
        back.setBackgroundColor(0x00000000);
        header.addView(back, new LinearLayout.LayoutParams(
                UiKit.dp(this, 44), UiKit.dp(this, 48)));
        TextView title = UiKit.label(this, "Добавить точку", 22, UiKit.TEXT);
        title.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        header.addView(title, new LinearLayout.LayoutParams(0, -2, 1));
        Button cancel = new Button(this);
        cancel.setText("Отмена");
        cancel.setTextColor(UiKit.GREEN_DARK);
        cancel.setTextSize(14);
        cancel.setAllCaps(false);
        cancel.setBackgroundColor(0x00000000);
        header.addView(cancel, new LinearLayout.LayoutParams(-2, UiKit.dp(this, 48)));
        root.addView(header);

        EditText input = new EditText(this);
        input.setSingleLine(true);
        input.setTextSize(16);
        input.setHint("Название места или адрес");
        input.setPadding(UiKit.dp(this, 14), 0, UiKit.dp(this, 14), 0);
        input.setBackground(UiKit.bordered(0xFFF5F7F5, 0xFFDDE4DF, 14, this));
        root.addView(input, new LinearLayout.LayoutParams(-1, UiKit.dp(this, 54)));

        TextView searchStatus = UiKit.label(this,
                "Начните вводить — покажем реальные места 2ГИС", 13, UiKit.MUTED);
        searchStatus.setPadding(UiKit.dp(this, 4), UiKit.dp(this, 12),
                UiKit.dp(this, 4), UiKit.dp(this, 8));
        root.addView(searchStatus);

        LinearLayout results = new LinearLayout(this);
        results.setOrientation(LinearLayout.VERTICAL);
        ScrollView resultsScroll = new ScrollView(this);
        resultsScroll.addView(results, new ScrollView.LayoutParams(-1, -2));
        root.addView(resultsScroll, new LinearLayout.LayoutParams(-1, 0, 1));

        dialog.setContentView(root);
        back.setOnClickListener(view -> dialog.dismiss());
        cancel.setOnClickListener(view -> dialog.dismiss());
        input.addTextChangedListener(new TextWatcher() {
            @Override public void beforeTextChanged(CharSequence s, int start, int count, int after) { }
            @Override public void onTextChanged(CharSequence s, int start, int before, int count) { }
            @Override public void afterTextChanged(Editable value) {
                schedulePlaceSearch(dialog, value.toString(), results, searchStatus);
            }
        });
        input.setOnEditorActionListener((view, actionId, event) -> {
            String text = input.getText().toString().trim();
            if (text.length() >= 2) {
                if (pendingPlaceSearch != null) uiHandler.removeCallbacks(pendingPlaceSearch);
                runPlaceSearch(dialog, text, ++searchGeneration, results, searchStatus);
            }
            return true;
        });
        dialog.setOnDismissListener(value -> {
            searchGeneration++;
            if (pendingPlaceSearch != null) uiHandler.removeCallbacks(pendingPlaceSearch);
            pendingPlaceSearch = null;
        });
        dialog.show();
        Window window = dialog.getWindow();
        if (window != null) {
            window.setLayout(WindowManager.LayoutParams.MATCH_PARENT,
                    WindowManager.LayoutParams.MATCH_PARENT);
            window.setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE
                    | WindowManager.LayoutParams.SOFT_INPUT_STATE_ALWAYS_VISIBLE);
        }
        input.requestFocus();
        input.postDelayed(() -> {
            InputMethodManager keyboard = (InputMethodManager)
                    getSystemService(Context.INPUT_METHOD_SERVICE);
            if (keyboard != null) {
                keyboard.showSoftInput(input, InputMethodManager.SHOW_IMPLICIT);
            }
        }, 180L);
    }

    private void schedulePlaceSearch(Dialog dialog, String rawText, LinearLayout results,
                                     TextView searchStatus) {
        if (pendingPlaceSearch != null) uiHandler.removeCallbacks(pendingPlaceSearch);
        int generation = ++searchGeneration;
        String text = rawText.trim();
        results.removeAllViews();
        if (text.length() < 2) {
            searchStatus.setText("Введите хотя бы два символа");
            return;
        }
        searchStatus.setText("Ищем в 2ГИС…");
        pendingPlaceSearch = () -> runPlaceSearch(dialog, text, generation,
                results, searchStatus);
        uiHandler.postDelayed(pendingPlaceSearch, 800L);
    }

    private void runPlaceSearch(Dialog dialog, String text, int generation,
                                LinearLayout results, TextView searchStatus) {
        String cityId = getIntent().getStringExtra(EXTRA_CITY_ID);
        String sessionId = getIntent().getStringExtra(EXTRA_SESSION_ID);
        network.execute(() -> {
            ApiClient.SearchResult response;
            try {
                response = ApiClient.searchPlaces(cityId, text, sessionId);
            } catch (Exception error) {
                response = new ApiClient.SearchResult(false,
                        "Не удалось выполнить поиск. Проверьте backend.", 0,
                        Collections.emptyList());
            }
            ApiClient.SearchResult finalResponse = response;
            runOnUiThread(() -> {
                if (!dialog.isShowing() || generation != searchGeneration
                        || isFinishing() || isDestroyed()) return;
                results.removeAllViews();
                searchStatus.setText(finalResponse.message);
                if (!finalResponse.success) return;
                for (ApiClient.PlaceOption place : finalResponse.items) {
                    results.addView(placeSearchRow(dialog, place, searchStatus),
                            new LinearLayout.LayoutParams(-1, UiKit.dp(this, 62)));
                }
            });
        });
    }

    private View placeSearchRow(Dialog dialog, ApiClient.PlaceOption place,
                                TextView searchStatus) {
        LinearLayout row = new LinearLayout(this);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.setPadding(UiKit.dp(this, 12), 0, UiKit.dp(this, 6), 0);
        row.setBackground(UiKit.bordered(0xFFFFFFFF, 0xFFE7ECE8, 12, this));
        TextView pin = UiKit.label(this, "●", 18, UiKit.GREEN);
        pin.setGravity(Gravity.CENTER);
        row.addView(pin, new LinearLayout.LayoutParams(UiKit.dp(this, 34), -1));
        TextView name = UiKit.label(this, place.name + (place.food ? "\nЗаведение" : "\nМесто 2ГИС"),
                15, UiKit.TEXT);
        name.setMaxLines(2);
        name.setEllipsize(android.text.TextUtils.TruncateAt.END);
        row.addView(name, new LinearLayout.LayoutParams(0, -2, 1));
        Button add = UiKit.button(this, "+", UiKit.GREEN, 0xFFFFFFFF);
        add.setTextSize(22);
        add.setPadding(0, 0, 0, 0);
        add.setMinWidth(0);
        add.setMinHeight(0);
        row.addView(add, new LinearLayout.LayoutParams(
                UiKit.dp(this, 44), UiKit.dp(this, 44)));
        View.OnClickListener listener = view -> addPlaceFromSearch(dialog, place, searchStatus);
        row.setOnClickListener(listener);
        add.setOnClickListener(listener);
        return row;
    }

    private void addPlaceFromSearch(Dialog dialog, ApiClient.PlaceOption place,
                                    TextView searchStatus) {
        for (ApiClient.PlaceOption current : editingPoints) {
            if (current.placeId.equals(place.placeId)) {
                searchStatus.setText("Эта точка уже есть в маршруте");
                return;
            }
        }
        if (editingPoints.size() >= 8) {
            searchStatus.setText("В маршруте может быть не больше восьми точек");
            return;
        }
        editingPoints.add(place);
        dialog.dismiss();
        renderEditablePointList();
        pointListScroll.post(() -> pointListScroll.fullScroll(View.FOCUS_DOWN));
    }

    private void startWalk() {
        if (isReadOnlyView() || startingWalk || route == null || !route.success || !routeServerBacked) return;
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
                        .putString("routeId", routeId).commit();
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
                    // A timeout must not erase the only local pointer to an
                    // ACTIVE backend walk.  Clear it only after a confirmed
                    // not-found response; the user can retry synchronization.
                    if ("NOT_FOUND".equals(walk.errorCode)) clearActiveWalk();
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
        boolean visiting = "VISITING".equals(walk.phase) && walk.currentPointOrder > 0;
        if (!visiting) {
            resetVisitingUi();
            stopVisitStopwatch();
            status.setText("◷  Осталось ≈" + walk.remainingMinutes + " мин"
                    + "              ●  Точка " + walk.currentPointOrder + " из "
                    + (route == null ? walk.currentPointOrder : route.points.size()));
        }
        if ("COMPLETED".equals(walk.status) || "STOPPED".equals(walk.status)) {
            guidancePanel.setVisibility(View.GONE);
            mapRouteSummary.setVisibility(View.VISIBLE);
            mapRouteSummary.setText("COMPLETED".equals(walk.status)
                    ? "Маршрут завершён" : "Прогулка остановлена");
        } else if (visiting) {
            startVisitStopwatch(pointName);
        } else if ("PAUSED".equals(walk.status)) {
            guidanceTitle.setText("Прогулка на паузе");
            guidanceSubtitle.setText("Продолжите, когда будете готовы");
            guidanceTurnIcon.setText("Ⅱ");
            mapRouteSummary.setVisibility(View.GONE);
            guidancePanel.setVisibility(View.VISIBLE);
        } else {
            updateGuidance(latestUserLat, latestUserLon);
        }
        renderPointList(walk.currentPointOrder, visiting);
        boolean active = "ACTIVE".equals(walk.status);
        boolean paused = "PAUSED".equals(walk.status);
        pauseResume.setVisibility(View.GONE);
        stopWalk.setEnabled(active || paused);
        primaryAction.setText("Ⅱ / ■");
        primaryAction.setContentDescription("Пауза или остановка прогулки");
        primaryAction.setTextColor(0xFFFFFFFF);
        primaryAction.setBackground(UiKit.rounded(paused ? 0xFF98A19D : UiKit.RED, 14, this));
        if (paused && !visiting) {
            mapRouteSummary.setVisibility(View.VISIBLE);
            mapRouteSummary.setText("Прогулка на паузе");
        }
        editQuery.setEnabled(active || paused);
        editPoints.setEnabled(active || paused);
        if ("COMPLETED".equals(walk.status) || "STOPPED".equals(walk.status)) {
            persistFinishedRoute();
            clearActiveWalk();
        }
        syncPartnerOffer();
    }

    private void startVisitStopwatch(String pointName) {
        stopVisitStopwatch();
        visitTimerBaseSeconds = Math.max(0, walk.visitElapsedSeconds);
        visitTimerSyncedAtElapsedMillis = SystemClock.elapsedRealtime();
        configureVisitingUi(pointName);
        renderVisitStopwatch(pointName);
        if (!"ACTIVE".equals(walk.status)) return;
        final String expectedWalkId = walk.walkId;
        final int expectedPointOrder = walk.currentPointOrder;
        visitTimerTick = new Runnable() {
            @Override public void run() {
                if (walk == null || !expectedWalkId.equals(walk.walkId)
                        || expectedPointOrder != walk.currentPointOrder
                        || !"VISITING".equals(walk.phase)
                        || !"ACTIVE".equals(walk.status)) {
                    visitTimerTick = null;
                    return;
                }
                renderVisitStopwatch(pointName);
                uiHandler.postDelayed(this, 1_000L);
            }
        };
        uiHandler.postDelayed(visitTimerTick, 1_000L);
    }

    private void renderVisitStopwatch(String pointName) {
        if (walk == null || !"VISITING".equals(walk.phase)) return;
        boolean running = "ACTIVE".equals(walk.status);
        int elapsed = VisitStopwatch.elapsedSeconds(visitTimerBaseSeconds,
                visitTimerSyncedAtElapsedMillis, SystemClock.elapsedRealtime(), running);
        String stopwatch = VisitStopwatch.format(elapsed);
        String timerLabel = running ? "На локации" : "На локации · пауза";
        SpannableString timer = new SpannableString(timerLabel + "\n" + stopwatch);
        timer.setSpan(new RelativeSizeSpan(0.43f), 0, timerLabel.length(),
                Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
        timer.setSpan(new android.text.style.ForegroundColorSpan(UiKit.MUTED),
                0, timerLabel.length(), Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
        timer.setSpan(new android.text.style.StyleSpan(Typeface.NORMAL),
                0, timerLabel.length(), Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
        status.setText(timer);
        status.setContentDescription(timerLabel + ", " + stopwatch);
    }

    private void configureVisitingUi(String pointName) {
        String structureKey = VisitingPresentation.structureRenderKey(route, walk);
        if (structureKey.equals(renderedVisitingStructureKey)) return;
        renderedVisitingStructureKey = structureKey;
        VisitingPresentation.Model model = VisitingPresentation.from(
                route, walk, Math.max(0, walk.visitElapsedSeconds), null);
        nextLabel.setText(model.pointLabel.toUpperCase(java.util.Locale.getDefault()));
        routeSummary.setText(model.pointName);
        status.setTextSize(compactScreen ? 29 : 33);
        status.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        status.setGravity(Gravity.START | Gravity.CENTER_VERTICAL);
        status.setIncludeFontPadding(true);
        status.setMinLines(2);
        status.setMaxLines(2);
        status.setLineSpacing(0f, 1f);
        int timerHeight = UiKit.dp(this, compactScreen ? 90 : 96);
        status.setMinHeight(timerHeight);
        status.setPadding(UiKit.dp(this, 14), UiKit.dp(this, 8),
                UiKit.dp(this, 16), UiKit.dp(this, 12));
        status.setBackground(UiKit.rounded(0xFFEAF7EE, 16, this));
        status.setTextColor(UiKit.GREEN_DARK);
        status.setCompoundDrawables(makeVisitClockIcon(), null, null, null);
        status.setCompoundDrawablePadding(UiKit.dp(this, 13));
        LinearLayout.LayoutParams timerParams = new LinearLayout.LayoutParams(-1, timerHeight);
        timerParams.topMargin = UiKit.dp(this, 8);
        timerParams.bottomMargin = UiKit.dp(this, 6);
        status.setLayoutParams(timerParams);

        visitingNextCard.setVisibility(model.showNext ? View.VISIBLE : View.GONE);
        visitingNextTitle.setText(model.nextTitle);
        visitingNextMeta.setText(model.nextMeta);
        visitingNextMeta.setVisibility(model.nextMeta.isEmpty() ? View.GONE : View.VISIBLE);
        pointListScroll.setVisibility(View.VISIBLE);
        renderPartnerOffer(model.partnerOffer);
        renderVisitArrivalCard(pointName);
    }

    private void renderVisitArrivalCard(String pointName) {
        guidanceLeadingIcon.setText("✓");
        guidanceLeadingIcon.setTextSize(27);
        guidanceLeadingIcon.setBackground(UiKit.rounded(UiKit.GREEN, 28, this));
        guidanceLeadingIcon.setTextColor(0xFFFFFFFF);
        guidanceTitle.setText("Вы на месте");
        guidanceSubtitle.setText(pointName + " · Вы в зоне локации");
        guidanceDivider.setVisibility(View.GONE);
        guidanceTurnIcon.setVisibility(View.GONE);
        mapRouteSummary.setVisibility(View.GONE);
        guidancePanel.setVisibility(View.VISIBLE);
    }

    private void renderPartnerOffer(VisitingPresentation.PartnerOffer offer) {
        if (!VisitingPresentation.shouldShowPartnerOffer(offer)) {
            partnerOfferView.setText("");
            partnerOfferButton.setText("Открыть в 2ГИС");
            partnerOfferCard.setVisibility(View.GONE);
            return;
        }
        String details = offer.title + "\n" + offer.venueName + " · "
                + offer.walkingMinutes + " мин пешком";
        if (offer.description != null && !offer.description.trim().isEmpty()) {
            details += "\n" + offer.description;
        }
        partnerOfferView.setText(details);
        partnerOfferButton.setText(offer.actionLabel);
        partnerOfferCard.setVisibility(View.VISIBLE);
    }

    private void syncPartnerOffer() {
        if (walk == null || !PartnerOfferRequestPolicy.eligible(
                walk.status, walk.phase, walk.currentPointOrder)) {
            invalidatePartnerOffer();
            return;
        }
        String key = PartnerOfferRequestPolicy.key(walk.walkId, walk.currentPointOrder);
        if (key.equals(routeViewModel.partnerOfferKey)) {
            renderPartnerOffer(VisitingPresentation.PartnerOffer.from(
                    routeViewModel.partnerOffer));
            return;
        }
        routeViewModel.partnerOfferKey = key;
        routeViewModel.partnerOffer = null;
        renderPartnerOffer(null);
        int generation = ++partnerOfferRequestGeneration;
        String walkId = walk.walkId;
        String sessionId = getIntent().getStringExtra(EXTRA_SESSION_ID);
        network.execute(() -> {
            ApiClient.PartnerOfferResult response;
            try {
                response = ApiClient.getPartnerOffer(walkId, sessionId);
            } catch (Exception error) {
                response = new ApiClient.PartnerOfferResult(false, null);
            }
            ApiClient.PartnerOfferResult finalResponse = response;
            runOnUiThread(() -> {
                if (isFinishing() || isDestroyed() || walk == null
                        || !PartnerOfferRequestPolicy.isCurrent(
                        key, generation, walk.walkId, walk.status, walk.phase,
                        walk.currentPointOrder, partnerOfferRequestGeneration)) return;
                routeViewModel.partnerOffer = finalResponse.success
                        ? finalResponse.offer : null;
                renderPartnerOffer(VisitingPresentation.PartnerOffer.from(
                        routeViewModel.partnerOffer));
            });
        });
    }

    private void invalidatePartnerOffer() {
        partnerOfferRequestGeneration++;
        routeViewModel.partnerOfferKey = null;
        routeViewModel.partnerOffer = null;
        renderPartnerOffer(null);
    }

    private void openPartnerOffer() {
        VisitingPresentation.PartnerOffer offer = VisitingPresentation.PartnerOffer.from(
                routeViewModel.partnerOffer);
        if (!VisitingPresentation.shouldShowPartnerOffer(offer)) return;
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(offer.actionUrl)));
        } catch (ActivityNotFoundException error) {
            Toast.makeText(this, "Не удалось открыть 2ГИС", Toast.LENGTH_SHORT).show();
        }
    }

    private void resetVisitingUi() {
        renderedVisitingStructureKey = null;
        visitingNextCard.setVisibility(View.GONE);
        pointListScroll.setVisibility(View.VISIBLE);
        invalidatePartnerOffer();
        nextLabel.setText("ПЕРВАЯ ТОЧКА");
        status.setTextSize(14);
        status.setTypeface(Typeface.DEFAULT, Typeface.NORMAL);
        status.setTextColor(UiKit.MUTED);
        status.setGravity(Gravity.CENTER_VERTICAL);
        status.setIncludeFontPadding(true);
        status.setMinLines(0);
        status.setMaxLines(Integer.MAX_VALUE);
        status.setMinHeight(0);
        status.setPadding(UiKit.dp(this, 14), 0, UiKit.dp(this, 14), 0);
        status.setBackground(UiKit.rounded(0xFFEAF9EF, 12, this));
        status.setCompoundDrawables(null, null, null, null);
        status.setCompoundDrawablePadding(0);
        LinearLayout.LayoutParams statusParams = new LinearLayout.LayoutParams(-1,
                UiKit.dp(this, compactScreen ? 40 : 46));
        statusParams.topMargin = UiKit.dp(this, 4);
        statusParams.bottomMargin = UiKit.dp(this, 4);
        status.setLayoutParams(statusParams);
        guidanceLeadingIcon.setText("🚶");
        guidanceLeadingIcon.setTextSize(25);
        guidanceLeadingIcon.setTextColor(UiKit.GREEN_DARK);
        guidanceLeadingIcon.setBackground(UiKit.rounded(0xFFE4F8EA, 28, this));
        guidanceDivider.setVisibility(View.VISIBLE);
        guidanceTurnIcon.setVisibility(View.VISIBLE);
    }

    private android.graphics.drawable.Drawable makeVisitClockIcon() {
        int size = UiKit.dp(this, compactScreen ? 38 : 42);
        Bitmap bitmap = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888);
        Canvas canvas = new Canvas(bitmap);
        Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
        float center = size / 2f;
        paint.setColor(0xFFDCEFE3);
        canvas.drawCircle(center, center, size * 0.48f, paint);
        paint.setStyle(Paint.Style.STROKE);
        paint.setStrokeWidth(Math.max(2f, size * 0.055f));
        paint.setStrokeCap(Paint.Cap.ROUND);
        paint.setColor(UiKit.GREEN_DARK);
        canvas.drawCircle(center, center, size * 0.26f, paint);
        canvas.drawLine(center, center, center, size * 0.34f, paint);
        canvas.drawLine(center, center, size * 0.66f, size * 0.54f, paint);
        android.graphics.drawable.BitmapDrawable drawable =
                new android.graphics.drawable.BitmapDrawable(getResources(), bitmap);
        drawable.setBounds(0, 0, size, size);
        return drawable;
    }

    private void stopVisitStopwatch() {
        if (visitTimerTick != null) {
            uiHandler.removeCallbacks(visitTimerTick);
            visitTimerTick = null;
        }
    }

    private boolean isOfflineView() {
        return route != null && route.success && !routeServerBacked;
    }

    private boolean isReadOnlyView() {
        return isOfflineView() || getIntent().getBooleanExtra(EXTRA_HISTORY_READ_ONLY, false);
    }

    private void releaseMapResources() {
        if (objects != null) objects.removeAll();
        objects = null;
        routeMarkerImages.clear();
        startMarkerImage = null;
        userMarkerImage = null;
        userMarker = null;
        map = null;
        logMemory("map-resources-released");
    }

    private void persistFinishedRoute() {
        String routeId = getIntent().getStringExtra(EXTRA_ROUTE_ID);
        if (routeId == null) return;
        // This marker is written by the map process itself before returning to
        // MainActivity. It also covers automatic completion and process death
        // between the STOP response and onActivityResult().
        getSharedPreferences(ROUTE_LIFECYCLE_PREFERENCES, MODE_PRIVATE).edit()
                .putString(FINISHED_ROUTE_ID, routeId).commit();
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
                handleWalkLocation(location, "continuous");
            }
            @Override public void onProviderDisabled(String provider) { }
            @Override public void onProviderEnabled(String provider) { }
            @Override public void onStatusChanged(String provider, int value, Bundle extras) { }
        };
        try {
            boolean requested = false;
            if (locationManager.isProviderEnabled(LocationManager.GPS_PROVIDER)) {
                locationManager.requestLocationUpdates(LocationManager.GPS_PROVIDER,
                        30_000L, 0f, locationListener, Looper.getMainLooper());
                requested = true;
            }
            if (locationManager.isProviderEnabled(LocationManager.NETWORK_PROVIDER)) {
                locationManager.requestLocationUpdates(LocationManager.NETWORK_PROVIDER,
                        30_000L, 0f, locationListener, Looper.getMainLooper());
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

    private void handleWalkLocation(Location location, String source) {
        if (location == null) return;
        latestUserLat = location.getLatitude();
        latestUserLon = location.getLongitude();
        latestUserAccuracy = location.hasAccuracy() ? location.getAccuracy() : Float.NaN;
        updateUserMarker(latestUserLat, latestUserLon);
        updateGuidance(latestUserLat, latestUserLon);
        debugLocation(source, location, distanceToCurrentPoint(location), "received");
        sendPosition(location);
    }

    private void sendPosition(Location location) {
        if (walk == null || !"ACTIVE".equals(walk.status)) return;
        int distance = distanceToCurrentPoint(location);
        double accuracy = location.hasAccuracy() ? location.getAccuracy() : 100.0;
        if (accuracy > PositionSubmissionPolicy.MAX_ACCURACY_METERS) {
            debugLocation("skip", location, distance, "accuracy");
            if (needsBoundaryConfirmation(distance)) {
                showGpsWaiting("Точность GPS недостаточна (±"
                        + Math.round(accuracy) + " м)");
            }
            return;
        }
        long nowElapsed = SystemClock.elapsedRealtime();
        long measuredElapsed = location.getElapsedRealtimeNanos() / 1_000_000L;
        if (!PositionSubmissionPolicy.isFresh(measuredElapsed, nowElapsed,
                routeViewModel.lastPositionMeasurementElapsedMillis)) {
            debugLocation("skip", location, distance, "stale-or-duplicate");
            return;
        }
        if (positionInFlight) {
            debugLocation("skip", location, distance, "request-in-flight");
            if (needsBoundaryConfirmation(distance)) {
                scheduleFreshConfirmation(PositionSubmissionPolicy.MIN_INTERVAL_MILLIS,
                        "ожидается завершение проверки");
            }
            return;
        }
        long delay = PositionSubmissionPolicy.delayUntilSlot(nowElapsed,
                routeViewModel.previousPositionSentAt, routeViewModel.latestPositionSentAt);
        if (delay > 0) {
            debugLocation("skip", location, distance, "local-rate-limit-" + delay);
            if (needsBoundaryConfirmation(distance)) {
                scheduleFreshConfirmation(delay, "повторная проверка доступна через "
                        + Math.max(1, (int) Math.ceil(delay / 1000.0)) + " сек");
            }
            return;
        }
        claimPositionSubmission(nowElapsed);
        routeViewModel.lastPositionMeasurementElapsedMillis = measuredElapsed;
        positionInFlight = true;
        String walkId = walk.walkId;
        String sessionId = getIntent().getStringExtra(EXTRA_SESSION_ID);
        int requestedPointOrder = walk.currentPointOrder;
        debugLocation("send", location, distance, "accepted");
        network.execute(() -> {
            ApiClient.WalkResult response;
            try {
                response = ApiClient.sendWalkPosition(
                        walkId, sessionId, location.getLatitude(), location.getLongitude(),
                        accuracy, location.getTime());
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
                    debugPositionResponse(finalResponse);
                    status.setText(finalResponse.message);
                    if ("RATE_LIMITED".equals(finalResponse.errorCode)
                            && walk != null && walkId.equals(walk.walkId)
                            && "ACTIVE".equals(walk.status)
                            && needsBoundaryConfirmation(distance)) {
                        scheduleFreshConfirmation(
                                Math.max(1, finalResponse.retryAfterSeconds) * 1_000L,
                                "backend временно ограничил проверку");
                    }
                    return;
                }
                if (walk == null || !walkId.equals(walk.walkId)
                        || !"ACTIVE".equals(walk.status)) return;
                walk = finalResponse;
                routeViewModel.walk = walk;
                debugPositionResponse(finalResponse);
                showWalkStatus();
                syncLocationTracking();
                if (!walk.pointReached && !walk.pointExited
                        && walk.currentPointOrder == requestedPointOrder
                        && needsBoundaryConfirmation(walk.distanceMeters)) {
                    long retryDelay = PositionSubmissionPolicy.delayUntilSlot(
                            SystemClock.elapsedRealtime(), routeViewModel.previousPositionSentAt,
                            routeViewModel.latestPositionSentAt);
                    scheduleFreshConfirmation(Math.max(
                            PositionSubmissionPolicy.MIN_INTERVAL_MILLIS, retryDelay),
                            "ожидается повторное GPS-измерение");
                }
            });
        });
    }

    private boolean needsBoundaryConfirmation(int distance) {
        if (walk == null || distance < 0) return false;
        if ("VISITING".equals(walk.phase)) return distance > EXIT_RADIUS_METERS;
        return distance <= ARRIVAL_RADIUS_METERS;
    }

    private void claimPositionSubmission(long now) {
        if (routeViewModel.previousPositionSentAt > now
                || routeViewModel.latestPositionSentAt > now) {
            routeViewModel.previousPositionSentAt = 0L;
            routeViewModel.latestPositionSentAt = 0L;
        }
        if (routeViewModel.latestPositionSentAt > now - PositionSubmissionPolicy.WINDOW_MILLIS) {
            routeViewModel.previousPositionSentAt = routeViewModel.latestPositionSentAt;
            routeViewModel.latestPositionSentAt = now;
        } else {
            routeViewModel.previousPositionSentAt = 0L;
            routeViewModel.latestPositionSentAt = now;
        }
    }

    private void scheduleFreshConfirmation(long delayMillis, String reason) {
        if (walk == null || !"ACTIVE".equals(walk.status) || isReadOnlyView()) return;
        if (pendingConfirmationRequest != null) {
            uiHandler.removeCallbacks(pendingConfirmationRequest);
        }
        final String expectedWalkId = walk.walkId;
        final int expectedPointOrder = walk.currentPointOrder;
        long safeDelay = Math.max(PositionSubmissionPolicy.MIN_INTERVAL_MILLIS, delayMillis);
        showGpsWaiting(reason);
        pendingConfirmationRequest = () -> {
            pendingConfirmationRequest = null;
            if (isFinishing() || isDestroyed() || walk == null
                    || !expectedWalkId.equals(walk.walkId)
                    || expectedPointOrder != walk.currentPointOrder
                    || !"ACTIVE".equals(walk.status)) return;
            requestFreshConfirmationLocation();
        };
        uiHandler.postDelayed(pendingConfirmationRequest, safeDelay);
        if (BuildConfig.DEBUG) Log.d(GEO_LOG, "confirmation scheduled: delayMs="
                + safeDelay + " pointOrder=" + expectedPointOrder + " reason=" + reason);
    }

    private void requestFreshConfirmationLocation() {
        if (locationManager == null || confirmationLocationListener != null) return;
        String provider = null;
        if (locationManager.isProviderEnabled(LocationManager.GPS_PROVIDER)) {
            provider = LocationManager.GPS_PROVIDER;
        } else if (locationManager.isProviderEnabled(LocationManager.NETWORK_PROVIDER)) {
            provider = LocationManager.NETWORK_PROVIDER;
        }
        if (provider == null) {
            showGpsWaiting("геопозиция выключена");
            return;
        }
        confirmationLocationListener = new LocationListener() {
            @Override public void onLocationChanged(Location location) {
                LocationListener completed = confirmationLocationListener;
                confirmationLocationListener = null;
                if (locationManager != null && completed != null) {
                    try { locationManager.removeUpdates(completed); }
                    catch (SecurityException ignored) { }
                }
                handleWalkLocation(location, "confirmation");
            }
            @Override public void onProviderDisabled(String name) { }
            @Override public void onProviderEnabled(String name) { }
            @Override public void onStatusChanged(String name, int value, Bundle extras) { }
        };
        try {
            locationManager.requestSingleUpdate(provider, confirmationLocationListener,
                    Looper.getMainLooper());
            showGpsWaiting("получаем повторное GPS-измерение");
            if (BuildConfig.DEBUG) Log.d(GEO_LOG,
                    "fresh confirmation requested: provider=" + provider);
        } catch (SecurityException error) {
            confirmationLocationListener = null;
            showGpsWaiting("нет разрешения на геопозицию");
        }
    }

    private int distanceToCurrentPoint(Location location) {
        if (location == null || walk == null || route == null || walk.currentPointOrder < 1
                || walk.currentPointOrder > route.points.size()) return -1;
        ApiClient.PlaceOption point = route.points.get(walk.currentPointOrder - 1);
        return (int) Math.round(meters(location.getLatitude(), location.getLongitude(),
                point.lat, point.lon));
    }

    private void showGpsWaiting(String reason) {
        if (guidancePanel == null || walk == null || !"ACTIVE".equals(walk.status)) return;
        if ("VISITING".equals(walk.phase) && route != null
                && walk.currentPointOrder > 0
                && walk.currentPointOrder <= route.points.size()) {
            renderVisitArrivalCard(route.points.get(walk.currentPointOrder - 1).name);
            return;
        }
        guidanceTitle.setText("VISITING".equals(walk.phase)
                ? "Подтверждаем выход с локации" : "Точка маршрута рядом");
        guidanceSubtitle.setText(reason);
        guidanceTurnIcon.setText("●");
        mapRouteSummary.setVisibility(View.GONE);
        guidancePanel.setVisibility(View.VISIBLE);
    }

    private void debugLocation(String action, Location location, int distance, String reason) {
        if (!BuildConfig.DEBUG || location == null) return;
        long age = Math.max(0L, SystemClock.elapsedRealtime()
                - location.getElapsedRealtimeNanos() / 1_000_000L);
        int pointOrder = walk == null ? 0 : walk.currentPointOrder;
        Log.d(GEO_LOG, String.format(java.util.Locale.US,
                "%s provider=%s lat=%.6f lon=%.6f ageMs=%d accuracy=%.1f pointOrder=%d distance=%d reason=%s",
                action, location.getProvider(), location.getLatitude(), location.getLongitude(),
                age, location.hasAccuracy() ? location.getAccuracy() : -1f,
                pointOrder, distance, reason));
    }

    private void debugPositionResponse(ApiClient.WalkResult response) {
        if (!BuildConfig.DEBUG || response == null) return;
        Log.d(GEO_LOG, "backend success=" + response.success
                + " pointReached=" + response.pointReached
                + " currentPointOrder=" + response.currentPointOrder
                + " distance=" + response.distanceMeters
                + " status=" + response.status
                + " phase=" + response.phase
                + " visitElapsed=" + response.visitElapsedSeconds
                + " pointExited=" + response.pointExited
                + " error=" + response.errorCode
                + " retryAfter=" + response.retryAfterSeconds);
    }

    private void sendWalkAction(String action) {
        if (isReadOnlyView() || walk == null || !walk.success) return;
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
                    stopWalk.setEnabled(controllable);
                    return;
                }
                walk = finalResponse;
                routeViewModel.walk = walk;
                showWalkStatus();
                syncLocationTracking();
                if ("STOP".equals(action)) {
                    Intent data = new Intent();
                    data.putExtra(EXTRA_RESULT_ACTION, ACTION_WALK_STOPPED);
                    data.putExtra(EXTRA_WALK_STATUS, finalResponse.status);
                    setResult(RESULT_OK, data);
                    finish();
                }
            });
        });
    }

    private void confirmStopWalk() {
        if (isReadOnlyView() || walk == null || !("ACTIVE".equals(walk.status) || "PAUSED".equals(walk.status))) {
            return;
        }
        new AlertDialog.Builder(this)
                .setTitle("Завершить прогулку?")
                .setMessage("Автоматическое прохождение будет остановлено.")
                .setNegativeButton("Отмена", null)
                .setPositiveButton("Завершить", (dialog, which) -> sendWalkAction("STOP"))
                .show();
    }

    private void showWalkMenu() {
        if (isReadOnlyView() || walk == null || !walk.success
                || !("ACTIVE".equals(walk.status) || "PAUSED".equals(walk.status))) {
            return;
        }
        boolean paused = "PAUSED".equals(walk.status);
        String[] actions = paused
                ? new String[]{"Продолжить прогулку", "Завершить прогулку"}
                : new String[]{"Поставить на паузу", "Завершить прогулку"};
        new AlertDialog.Builder(this)
                .setTitle("Управление прогулкой")
                .setItems(actions, (dialog, which) -> {
                    if (which == 0) {
                        sendWalkAction(paused ? "RESUME" : "PAUSE");
                    } else {
                        confirmStopWalk();
                    }
                })
                .show();
    }

    private void returnForEdit(String action) {
        Intent data = new Intent();
        data.putExtra(EXTRA_RESULT_ACTION, action);
        if (walk != null && walk.success && ("ACTIVE".equals(walk.status)
                || "PAUSED".equals(walk.status))) {
            data.putExtra(EXTRA_WALK_ID, walk.walkId);
            data.putExtra(EXTRA_ROUTE_ID, getIntent().getStringExtra(EXTRA_ROUTE_ID));
        }
        setResult(RESULT_OK, data);
        finish();
    }

    private void returnToMain() {
        Intent data = new Intent();
        if (walk != null && walk.success && ("ACTIVE".equals(walk.status)
                || "PAUSED".equals(walk.status))) {
            data.putExtra(EXTRA_WALK_ID, walk.walkId);
            data.putExtra(EXTRA_ROUTE_ID, getIntent().getStringExtra(EXTRA_ROUTE_ID));
        }
        setResult(RESULT_OK, data);
        finish();
    }

    private void confirmCancelRoute() {
        if (isReadOnlyView() || startingWalk) return;
        new AlertDialog.Builder(this)
                .setTitle("Отменить маршрут?")
                .setMessage("Текущий маршрут будет полностью сброшен.")
                .setNegativeButton("Оставить", null)
                .setPositiveButton("Отменить маршрут", (dialog, which) -> cancelRoute())
                .show();
    }

    private void cancelRoute() {
        if (isReadOnlyView()) return;
        startingWalk = true;
        primaryAction.setEnabled(false);
        editQuery.setEnabled(false);
        editPoints.setEnabled(false);
        status.setText("Отменяем маршрут…");
        String routeId = getIntent().getStringExtra(EXTRA_ROUTE_ID);
        String sessionId = getIntent().getStringExtra(EXTRA_SESSION_ID);
        network.execute(() -> {
            String failure = null;
            try {
                ApiClient.WalkResult walkToStop = walk;
                if (walkToStop == null || !walkToStop.success
                        || !("ACTIVE".equals(walkToStop.status) || "PAUSED".equals(walkToStop.status))) {
                    walkToStop = ApiClient.getActiveWalk(routeId, sessionId);
                }
                if (walkToStop.success && ("ACTIVE".equals(walkToStop.status)
                        || "PAUSED".equals(walkToStop.status))) {
                    ApiClient.WalkResult stopped = ApiClient.walkAction(walkToStop.walkId, sessionId, "STOP");
                    if (!stopped.success) failure = stopped.message;
                } else if (!walkToStop.success && !"NOT_FOUND".equals(walkToStop.errorCode)) {
                    failure = walkToStop.message;
                }
            } catch (Exception error) { failure = "Не удалось завершить прогулку. Проверьте backend."; }
            if (failure == null) {
                try {
                    ApiClient.Result deleted = ApiClient.deleteRoute(routeId, sessionId);
                    if (!deleted.success) failure = deleted.message;
                } catch (Exception error) { failure = "Не удалось отменить маршрут. Проверьте backend."; }
            }
            String finalFailure = failure;
            runOnUiThread(() -> {
                if (isFinishing() || isDestroyed()) return;
                if (finalFailure != null) {
                    startingWalk = false;
                    primaryAction.setEnabled(true);
                    editQuery.setEnabled(true);
                    editPoints.setEnabled(true);
                    status.setText(finalFailure);
                    return;
                }
                clearActiveWalk();
                Intent data = new Intent();
                data.putExtra(EXTRA_RESULT_ACTION, ACTION_CANCEL_ROUTE);
                setResult(RESULT_OK, data);
                finish();
            });
        });
    }

    @Override public void onBackPressed() {
        if (pointEditing) cancelPointEditing();
        else returnToMain();
    }

    private void stopLocationTracking() {
        if (pendingConfirmationRequest != null) {
            uiHandler.removeCallbacks(pendingConfirmationRequest);
            pendingConfirmationRequest = null;
        }
        if (locationManager != null && locationListener != null) {
            try { locationManager.removeUpdates(locationListener); }
            catch (SecurityException ignored) { }
        }
        if (locationManager != null && confirmationLocationListener != null) {
            try { locationManager.removeUpdates(confirmationLocationListener); }
            catch (SecurityException ignored) { }
        }
        locationListener = null;
        confirmationLocationListener = null;
    }

    @Override protected void onStart() {
        super.onStart();
        if (walk != null && walk.success) {
            showWalkStatus();
            syncLocationTracking();
        }
    }

    @Override public void onTrimMemory(int level) {
        super.onTrimMemory(level);
        if (map == null && level >= android.content.ComponentCallbacks2.TRIM_MEMORY_RUNNING_LOW) {
            mapInitializationStarted = false;
        }
    }

    @Override protected void onStop() {
        stopVisitStopwatch();
        stopLocationTracking();
        super.onStop();
    }

    private void clearActiveWalk() {
        getSharedPreferences("active_walk", MODE_PRIVATE).edit().clear().commit();
        stopLocationTracking();
    }

    private void renderRoute() {
        renderRoute(false);
    }

    private void renderRoute(boolean fitCameraToRoute) {
        if (map == null || route == null || !route.success) return;
        if (objects == null) objects = new MapObjectManager(map, null);
        else objects.removeAll();

        GulyayApplication application = (GulyayApplication) getApplication();
        routeMarkerImages.clear();
        double startLat = routeStartLat();
        double startLon = routeStartLon();
        boolean startsFromUser = "USER_GEO".equals(route.startSource);
        if (!startsFromUser && Double.isFinite(startLat) && Double.isFinite(startLon)) {
            startMarkerImage = labeledPinImage(application, "S", "Старт маршрута", 0xFFFF8A34);
            routeMarkerImages.add(startMarkerImage);
            objects.addObject(new Marker(labeledMarkerOptions(startLat, startLon,
                    startMarkerImage, "Старт маршрута", route.points.size() + 20)));
        }
        for (int i = 0; i < route.points.size(); i++) {
            ApiClient.PlaceOption point = route.points.get(i);
            if (!Double.isFinite(point.lat) || !Double.isFinite(point.lon)) continue;
            Image numbered = labeledPinImage(application, String.valueOf(i + 1),
                    point.name, 0xFF00A83E);
            routeMarkerImages.add(numbered);
            MarkerOptions options = labeledMarkerOptions(point.lat, point.lon, numbered,
                    point.name, i + 2);
            objects.addObject(new Marker(options));
        }

        if (route.path.size() >= 2) {
            List<GeoPoint> geometry = new ArrayList<>(route.path.size());
            for (ApiClient.GeoCoordinate coordinate : route.path) {
                geometry.add(GeoPointExtraKt.GeoPoint(coordinate.lat, coordinate.lon));
            }
            PolylineOptions line = new PolylineOptions(
                    geometry, new LogicalPixel(5f), new Color(0xFF00A88F),
                    0.0, null, null, true, "route", new ZIndex(1), null, null);
            objects.addObject(new Polyline(line));
        }

        userMarker = null;
        double markerLat = latestUserLat;
        double markerLon = latestUserLon;
        if (startsFromUser && (!Double.isFinite(markerLat) || !Double.isFinite(markerLon))) {
            markerLat = startLat;
            markerLon = startLon;
        }
        updateUserMarker(markerLat, markerLon);

        if ((fitCameraToRoute || !restoredCamera) && !route.path.isEmpty()) {
            double[] bounds = routeBounds(route.path);
            rememberRouteCameraBounds(route.path, bounds);
            map.getCamera().move(camera(bounds[0], bounds[1], (float) bounds[2]),
                    Duration.ofMilliseconds(0), CameraAnimationType.LINEAR);
        } else if (!route.path.isEmpty()) {
            rememberRouteCameraBounds(route.path, routeBounds(route.path));
        }
        renderedRouteVersion = route.routeVersion;
    }

    private void rememberRouteCameraBounds(List<ApiClient.GeoCoordinate> path, double[] bounds) {
        routeMinLat = 90;
        routeMaxLat = -90;
        routeMinLon = 180;
        routeMaxLon = -180;
        for (ApiClient.GeoCoordinate coordinate : path) {
            routeMinLat = Math.min(routeMinLat, coordinate.lat);
            routeMaxLat = Math.max(routeMaxLat, coordinate.lat);
            routeMinLon = Math.min(routeMinLon, coordinate.lon);
            routeMaxLon = Math.max(routeMaxLon, coordinate.lon);
        }
        double latPadding = Math.max(0.003, (routeMaxLat - routeMinLat) * 0.15);
        double lonPadding = Math.max(0.005, (routeMaxLon - routeMinLon) * 0.15);
        routeMinLat -= latPadding;
        routeMaxLat += latPadding;
        routeMinLon -= lonPadding;
        routeMaxLon += lonPadding;
        routeCenterLat = bounds[0];
        routeCenterLon = bounds[1];
        routeZoom = (float) bounds[2];
        routeMinZoom = routeZoom;
        routeCameraReady = true;
    }

    private void changeMapZoom(float delta) {
        if (map == null) return;
        CameraSnapshot snapshot = cameraSnapshot();
        double lat = snapshot == null ? routeCenterLat : snapshot.lat;
        double lon = snapshot == null ? routeCenterLon : snapshot.lon;
        float currentZoom = snapshot == null ? routeZoom : snapshot.zoom;
        float nextZoom = Math.max(routeMinZoom, Math.min(18f, currentZoom + delta));
        if (routeCameraReady) {
            lat = Math.max(routeMinLat, Math.min(routeMaxLat, lat));
            lon = Math.max(routeMinLon, Math.min(routeMaxLon, lon));
        }
        routeCenterLat = lat;
        routeCenterLon = lon;
        routeZoom = nextZoom;
        map.getCamera().move(camera(lat, lon, nextZoom), Duration.ofMilliseconds(180),
                CameraAnimationType.LINEAR);
    }

    private void enforceRouteCameraBounds() {
        if (map == null || !routeCameraReady || isFinishing() || isDestroyed()) return;
        CameraSnapshot snapshot = cameraSnapshot();
        if (snapshot == null) {
            map.getCamera().move(camera(routeCenterLat, routeCenterLon,
                            Math.max(routeMinZoom, routeZoom)),
                    Duration.ofMilliseconds(120), CameraAnimationType.LINEAR);
            return;
        }
        double lat = Math.max(routeMinLat, Math.min(routeMaxLat, snapshot.lat));
        double lon = Math.max(routeMinLon, Math.min(routeMaxLon, snapshot.lon));
        float zoom = Math.max(routeMinZoom, Math.min(18f, snapshot.zoom));
        routeCenterLat = lat;
        routeCenterLon = lon;
        routeZoom = zoom;
        if (Math.abs(lat - snapshot.lat) < 0.000001
                && Math.abs(lon - snapshot.lon) < 0.000001
                && Math.abs(zoom - snapshot.zoom) < 0.01f) return;
        map.getCamera().move(camera(lat, lon, zoom), Duration.ofMilliseconds(180),
                CameraAnimationType.LINEAR);
    }

    private CameraSnapshot cameraSnapshot() {
        try {
            Object position = map.getCamera().getClass().getMethod("getPosition")
                    .invoke(map.getCamera());
            Object point = position.getClass().getMethod("getPoint").invoke(position);
            Object latitude = point.getClass().getMethod("getLatitude").invoke(point);
            Object longitude = point.getClass().getMethod("getLongitude").invoke(point);
            Object zoom = position.getClass().getMethod("getZoom").invoke(position);
            double lat = numericValue(latitude);
            double lon = numericValue(longitude);
            float zoomValue = (float) numericValue(zoom);
            return new CameraSnapshot(lat, lon, zoomValue);
        } catch (ReflectiveOperationException | ClassCastException error) {
            if (!cameraSnapshotFailureLogged) {
                cameraSnapshotFailureLogged = true;
                Log.w(MEMORY_LOG, "Cannot read 2GIS camera position; using safe route center", error);
            }
            return null;
        }
    }

    private static double numericValue(Object value) throws ReflectiveOperationException {
        if (value instanceof Number) return ((Number) value).doubleValue();
        Object raw = value.getClass().getMethod("getValue").invoke(value);
        if (!(raw instanceof Number)) throw new ClassCastException();
        return ((Number) raw).doubleValue();
    }

    private Image labeledPinImage(GulyayApplication application, String label,
                                  String placeName, int color) {
        int width = UiKit.dp(this, 176);
        int height = UiKit.dp(this, 62);
        Bitmap bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888);
        Canvas canvas = new Canvas(bitmap);
        Paint fill = new Paint(Paint.ANTI_ALIAS_FLAG);
        fill.setColor(color);
        float centerX = UiKit.dp(this, 23);
        float centerY = UiKit.dp(this, 22);
        float radius = UiKit.dp(this, 18);
        Path pin = new Path();
        pin.addCircle(centerX, centerY, radius, Path.Direction.CW);
        pin.moveTo(centerX - UiKit.dp(this, 11), centerY + UiKit.dp(this, 13));
        pin.lineTo(centerX, UiKit.dp(this, 58));
        pin.lineTo(centerX + UiKit.dp(this, 11), centerY + UiKit.dp(this, 13));
        pin.close();
        canvas.drawPath(pin, fill);
        Paint border = new Paint(Paint.ANTI_ALIAS_FLAG);
        border.setStyle(Paint.Style.STROKE);
        border.setStrokeJoin(Paint.Join.ROUND);
        border.setStrokeWidth(UiKit.dp(this, 2));
        border.setColor(0xFFFFFFFF);
        canvas.drawPath(pin, border);
        Paint text = new Paint(Paint.ANTI_ALIAS_FLAG);
        text.setColor(0xFFFFFFFF);
        text.setTypeface(Typeface.DEFAULT_BOLD);
        text.setTextAlign(Paint.Align.CENTER);
        text.setTextSize(UiKit.dp(this, label.length() > 1 ? 14 : 17));
        Paint.FontMetrics metrics = text.getFontMetrics();
        float baseline = centerY - (metrics.ascent + metrics.descent) / 2f;
        canvas.drawText(label, centerX, baseline, text);

        String safeName = placeName == null || placeName.trim().isEmpty()
                ? "Точка маршрута" : placeName.trim();
        Paint name = new Paint(Paint.ANTI_ALIAS_FLAG);
        name.setTypeface(Typeface.DEFAULT_BOLD);
        name.setTextSize(UiKit.dp(this, 13));
        name.setTextAlign(Paint.Align.LEFT);
        float nameX = UiKit.dp(this, 47);
        float maxNameWidth = width - nameX - UiKit.dp(this, 3);
        List<String> lines = markerTextLines(safeName, name, maxNameWidth);
        float firstBaseline = lines.size() > 1 ? UiKit.dp(this, 23) : UiKit.dp(this, 31);
        for (int i = 0; i < lines.size(); i++) {
            float y = firstBaseline + i * UiKit.dp(this, 17);
            name.setStyle(Paint.Style.STROKE);
            name.setStrokeJoin(Paint.Join.ROUND);
            name.setStrokeWidth(UiKit.dp(this, 3));
            name.setColor(0xEEFFFFFF);
            canvas.drawText(lines.get(i), nameX, y, name);
            name.setStyle(Paint.Style.FILL);
            name.setColor(0xFF202522);
            canvas.drawText(lines.get(i), nameX, y, name);
        }
        return ImagesKt.imageFromBitmap(application.sdkContext(), bitmap);
    }

    private static List<String> markerTextLines(String value, Paint paint, float maxWidth) {
        List<String> lines = new ArrayList<>(2);
        String rest = value.replace('\n', ' ').replaceAll("\\s+", " ").trim();
        for (int line = 0; line < 2 && !rest.isEmpty(); line++) {
            int count = paint.breakText(rest, true, maxWidth, null);
            if (count >= rest.length()) {
                lines.add(rest);
                rest = "";
                break;
            }
            int split = rest.lastIndexOf(' ', Math.max(1, count));
            if (split <= 0) split = count;
            String part = rest.substring(0, split).trim();
            rest = rest.substring(split).trim();
            if (line == 1 && !rest.isEmpty()) {
                String suffix = "…";
                while (!part.isEmpty() && paint.measureText(part + suffix) > maxWidth) {
                    part = part.substring(0, part.length() - 1).trim();
                }
                part += suffix;
                rest = "";
            }
            lines.add(part);
        }
        if (lines.isEmpty()) lines.add("Точка маршрута");
        return lines;
    }

    private Image userLocationImage(GulyayApplication application) {
        int size = UiKit.dp(this, 56);
        Bitmap bitmap = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888);
        Canvas canvas = new Canvas(bitmap);
        float center = size / 2f;
        Paint accuracy = new Paint(Paint.ANTI_ALIAS_FLAG);
        accuracy.setColor(0x332474FF);
        canvas.drawCircle(center, center, UiKit.dp(this, 26), accuracy);
        Paint white = new Paint(Paint.ANTI_ALIAS_FLAG);
        white.setColor(0xFFFFFFFF);
        canvas.drawCircle(center, center, UiKit.dp(this, 12), white);
        Paint blue = new Paint(Paint.ANTI_ALIAS_FLAG);
        blue.setColor(0xFF2474FF);
        canvas.drawCircle(center, center, UiKit.dp(this, 9), blue);
        return ImagesKt.imageFromBitmap(application.sdkContext(), bitmap);
    }

    private void updateUserMarker(double lat, double lon) {
        if (map == null || objects == null || !Double.isFinite(lat) || !Double.isFinite(lon)) {
            return;
        }
        GeoPointWithElevation position = GeoPointWithElevationExtraKt.GeoPointWithElevation(
                lat, lon, new Elevation());
        if (userMarker != null) {
            userMarker.setPosition(position);
            return;
        }
        GulyayApplication application = (GulyayApplication) getApplication();
        if (userMarkerImage == null) {
            userMarkerImage = userLocationImage(application);
        }
        userMarker = new Marker(userMarkerOptions(
                lat, lon, userMarkerImage, route.points.size() + 30));
        objects.addObject(userMarker);
    }

    private void updateGuidance(double lat, double lon) {
        if (walk == null || !walk.success || route == null || !route.success
                || route.path.size() < 2 || walk.currentPointOrder < 1
                || walk.currentPointOrder > route.points.size()) return;
        if ("VISITING".equals(walk.phase)) {
            renderVisitStopwatch(route.points.get(walk.currentPointOrder - 1).name);
            return;
        }
        if (!Double.isFinite(lat) || !Double.isFinite(lon)) {
            lat = routeStartLat();
            lon = routeStartLon();
        }
        ApiClient.PlaceOption target = route.points.get(walk.currentPointOrder - 1);
        GuidanceInfo guidance = guidanceInfo(lat, lon, target);
        guidanceTitle.setText(guidance.title);
        guidanceSubtitle.setText(guidance.subtitle);
        guidanceTurnIcon.setText(guidance.icon);
        mapRouteSummary.setVisibility(View.GONE);
        guidancePanel.setVisibility(View.VISIBLE);
    }

    private GuidanceInfo guidanceInfo(double lat, double lon, ApiClient.PlaceOption target) {
        if (!Double.isFinite(lat) || !Double.isFinite(lon)) {
            return new GuidanceInfo("Следуйте по линии маршрута",
                    "До " + target.name, "↑");
        }
        int directMeters = (int) Math.round(meters(lat, lon, target.lat, target.lon));
        if (directMeters <= ARRIVAL_RADIUS_METERS) {
            String title = directMeters <= 35 ? "Вы у точки" : "Точка маршрута рядом";
            String subtitle;
            if (Float.isFinite(latestUserAccuracy)
                    && latestUserAccuracy > PositionSubmissionPolicy.MAX_ACCURACY_METERS) {
                subtitle = "Точность GPS недостаточна (±"
                        + Math.round(latestUserAccuracy) + " м)";
            } else if (walk != null && !walk.pointReached) {
                subtitle = "Ожидаем повторное GPS-измерение для подтверждения";
            } else {
                subtitle = "До " + target.name + " — " + directMeters + " м";
            }
            return new GuidanceInfo(title, subtitle, "●");
        }

        List<ApiClient.GeoCoordinate> leg = currentLegPath();
        if (leg.size() < 2) {
            return new GuidanceInfo("Следуйте по линии маршрута",
                    "До " + target.name, "↑");
        }
        if (routeViewModel.guidancePointOrder != walk.currentPointOrder) {
            routeViewModel.guidancePointOrder = walk.currentPointOrder;
            routeViewModel.guidancePathIndex = 0;
        }
        List<WalkGuidanceMath.Point> path = new ArrayList<>(leg.size());
        for (ApiClient.GeoCoordinate point : leg) {
            path.add(new WalkGuidanceMath.Point(point.lat, point.lon));
        }
        WalkGuidanceMath.Result remaining = WalkGuidanceMath.remainingOnLeg(path, lat, lon,
                routeViewModel.guidancePathIndex);
        routeViewModel.guidancePathIndex = remaining.nearestIndex;
        int nearest = remaining.nearestIndex;
        int targetIndex = leg.size() - 1;
        int targetMeters = remaining.distanceMeters;
        int walkingMinutes = Math.max(1, (int) Math.ceil(targetMeters / 80.0));
        String subtitle = "До " + target.name + " — ≈" + walkingMinutes + " мин";

        TurnHint turn = nextTurn(leg, nearest, targetIndex);
        if (turn != null) {
            String arrow = "направо".equals(turn.direction) ? "↱" : "↰";
            if (turn.distanceMeters <= 40) {
                return new GuidanceInfo("Поверните " + turn.direction, subtitle, arrow);
            }
            return new GuidanceInfo("Через " + roundedMeters(turn.distanceMeters)
                    + " поверните " + turn.direction, subtitle, arrow);
        }
        return new GuidanceInfo("Продолжайте прямо " + roundedMeters(targetMeters),
                subtitle, "↑");
    }

    private List<ApiClient.GeoCoordinate> currentLegPath() {
        if (route == null || walk == null || route.legGeometries == null) {
            return Collections.emptyList();
        }
        for (ApiClient.RouteLegGeometry leg : route.legGeometries) {
            if (leg.toOrder == walk.currentPointOrder) return leg.path;
        }
        return Collections.emptyList();
    }

    private TurnHint nextTurn(List<ApiClient.GeoCoordinate> path, int start, int end) {
        if (end - start < 2) return null;
        double previousBearing = Double.NaN;
        double accumulated = 0;
        for (int i = start; i < end; i++) {
            ApiClient.GeoCoordinate from = path.get(i);
            ApiClient.GeoCoordinate to = path.get(i + 1);
            double segment = meters(from.lat, from.lon, to.lat, to.lon);
            if (segment < 3) continue;
            double currentBearing = bearing(from.lat, from.lon, to.lat, to.lon);
            if (Double.isFinite(previousBearing) && accumulated >= 20) {
                double delta = normalizeBearing(currentBearing - previousBearing);
                if (Math.abs(delta) >= 35 && Math.abs(delta) <= 150) {
                    return new TurnHint((int) Math.round(accumulated),
                            delta > 0 ? "направо" : "налево");
                }
            }
            previousBearing = currentBearing;
            accumulated += segment;
            if (accumulated > 700) break;
        }
        return null;
    }

    private static String roundedMeters(int meters) {
        if (meters < 100) return Math.max(10, (int) Math.round(meters / 10.0) * 10) + " м";
        if (meters < 1000) return ((int) Math.round(meters / 50.0) * 50) + " м";
        return String.format(java.util.Locale.US, "%.1f км", meters / 1000.0);
    }

    private static double meters(double lat1, double lon1, double lat2, double lon2) {
        return WalkGuidanceMath.meters(lat1, lon1, lat2, lon2);
    }

    private static double bearing(double lat1, double lon1, double lat2, double lon2) {
        double first = Math.toRadians(lat1);
        double second = Math.toRadians(lat2);
        double deltaLon = Math.toRadians(lon2 - lon1);
        double y = Math.sin(deltaLon) * Math.cos(second);
        double x = Math.cos(first) * Math.sin(second)
                - Math.sin(first) * Math.cos(second) * Math.cos(deltaLon);
        return Math.toDegrees(Math.atan2(y, x));
    }

    private static double normalizeBearing(double value) {
        while (value > 180) value -= 360;
        while (value < -180) value += 360;
        return value;
    }

    private double routeStartLat() {
        if (route != null && Double.isFinite(route.startLat)) return route.startLat;
        return route != null && !route.path.isEmpty() ? route.path.get(0).lat : Double.NaN;
    }

    private double routeStartLon() {
        if (route != null && Double.isFinite(route.startLon)) return route.startLon;
        return route != null && !route.path.isEmpty() ? route.path.get(0).lon : Double.NaN;
    }

    private static double[] cityCenter(String cityId) {
        if ("moscow".equals(cityId)) return new double[]{55.7558, 37.6173};
        if ("vladimir".equals(cityId)) return new double[]{56.1291, 40.4075};
        if ("borovsk".equals(cityId)) return new double[]{55.2073, 36.4833};
        return new double[]{54.1930, 37.6178};
    }

    private static final class CameraSnapshot {
        final double lat;
        final double lon;
        final float zoom;

        CameraSnapshot(double lat, double lon, float zoom) {
            this.lat = lat;
            this.lon = lon;
            this.zoom = zoom;
        }
    }

    private static MarkerOptions labeledMarkerOptions(double lat, double lon, Image icon,
                                                       String name, int zIndex) {
        GeoPointWithElevation position = GeoPointWithElevationExtraKt.GeoPointWithElevation(
                lat, lon, new Elevation());
        return new MarkerOptions(
                position, icon, null, new Anchor(23f / 176f, 58f / 62f), null,
                (TextStyle) null, new Opacity(1f), true, false,
                new LogicalPixel(176f), name,
                new ZIndex(zIndex), new LabelingPriority((byte) 100), true,
                null, AnimationMode.NORMAL, false);
    }

    private static MarkerOptions userMarkerOptions(double lat, double lon, Image icon,
                                                    int zIndex) {
        GeoPointWithElevation position = GeoPointWithElevationExtraKt.GeoPointWithElevation(
                lat, lon, new Elevation());
        return new MarkerOptions(
                position, icon, null, new Anchor(0.5f, 0.5f), null, (TextStyle) null,
                new Opacity(1f), true, false, new LogicalPixel(56f), "Вы здесь",
                new ZIndex(zIndex), new LabelingPriority((byte) 100), true,
                null, AnimationMode.NORMAL, false);
    }

    private static final class GuidanceInfo {
        final String title;
        final String subtitle;
        final String icon;

        GuidanceInfo(String title, String subtitle, String icon) {
            this.title = title;
            this.subtitle = subtitle;
            this.icon = icon;
        }
    }

    private static final class TurnHint {
        final int distanceMeters;
        final String direction;

        TurnHint(int distanceMeters, String direction) {
            this.distanceMeters = distanceMeters;
            this.direction = direction;
        }
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
        uiHandler.removeCallbacksAndMessages(null);
        stopLocationTracking();
        releaseMapResources();
        if (mapView != null) {
            getLifecycle().removeObserver(mapView);
            if (mapView.getParent() == mapContainer) mapContainer.removeView(mapView);
            mapView = null;
        }
        network.shutdownNow();
        logMemory("destroyed");
        super.onDestroy();
    }

    public static final class RouteViewModel extends ViewModel {
        ApiClient.Result route;
        ApiClient.WalkResult walk;
        long previousPositionSentAt;
        long latestPositionSentAt;
        long lastPositionMeasurementElapsedMillis;
        int guidancePointOrder;
        int guidancePathIndex;
        String partnerOfferKey;
        ApiClient.PartnerOffer partnerOffer;
    }
}
