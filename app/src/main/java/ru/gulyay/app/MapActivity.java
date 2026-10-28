package ru.gulyay.app;

import android.Manifest;
import android.app.ActivityManager;
import android.app.AlertDialog;
import android.app.Dialog;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.res.ColorStateList;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.Typeface;
import android.location.Location;
import android.location.LocationListener;
import android.location.LocationManager;
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
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.SeekBar;
import android.widget.TextView;
import android.widget.Toast;
import androidx.activity.ComponentActivity;
import androidx.coordinatorlayout.widget.CoordinatorLayout;
import androidx.core.content.ContextCompat;
import androidx.lifecycle.ViewModel;
import androidx.lifecycle.ViewModelProvider;
import androidx.media3.common.MediaItem;
import androidx.media3.common.PlaybackException;
import androidx.media3.common.Player;
import androidx.media3.session.MediaController;
import androidx.media3.session.SessionToken;
import com.google.android.material.bottomsheet.BottomSheetBehavior;
import com.google.common.util.concurrent.ListenableFuture;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
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
    private static final String PANEL_STATE_PREFIX = "panel_state_";
    private static final String AUDIO_GUIDE_PREFERENCES = "audio_guide_ui";
    private static final int AUDIO_NOTIFICATION_REQUEST = 209;

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
    private LinearLayout panelScrollableContent;
    private LinearLayout actions;
    private TextView photoPlaceholder;
    private LinearLayout visitingNextCard;
    private TextView visitingNextIcon;
    private TextView visitingNextTitle;
    private TextView visitingNextMeta;
    private LinearLayout partnerOfferCard;
    private ImageView partnerOfferImage;
    private TextView partnerDisclosure;
    private TextView partnerOfferView;
    private TextView partnerOfferMeta;
    private TextView partnerOfferDismiss;
    private Button partnerOfferButton;
    private boolean partnerOfferInsertInFlight;
    private LinearLayout audioCard;
    private LinearLayout audioNewStoryBanner;
    private TextView audioNewStoryTitle;
    private ImageView audioAvailableIcon;
    private TextView audioStateLabel;
    private TextView audioStoryTitle;
    private LinearLayout audioStoryTextContainer;
    private TextView audioDuration;
    private Button audioListenButton;
    private LinearLayout audioPlayerControls;
    private SeekBar audioSeekBar;
    private TextView audioElapsed;
    private TextView audioTotal;
    private Button audioRewind;
    private Button audioPlayPause;
    private Button audioForward;
    private TextView audioClose;
    private TextView audioError;
    private Button audioNextButton;
    private final AudioGuideCoordinator audioCoordinator = new AudioGuideCoordinator();
    private final java.util.Map<String, AudioStoryCatalog.AvailableStory> availableAudioStories =
            new HashMap<>();
    private final ExecutorService audioIo = Executors.newSingleThreadExecutor();
    private ListenableFuture<MediaController> audioControllerFuture;
    private MediaController audioController;
    private int audioInspectionGeneration;
    private boolean audioSeekInProgress;
    private boolean audioStateRestored;
    private String audioLastError;
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
    private BottomSheetBehavior<LinearLayout> routeSheetBehavior;
    private LinearLayout routeSheetView;
    private String panelRouteKey;
    private boolean applyingPanelState;
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
    private final Runnable audioProgressTick = new Runnable() {
        @Override public void run() {
            renderAudioGuide();
            expireAudioGuideIfNeeded();
            if (audioCard != null && audioCard.getVisibility() == View.VISIBLE) {
                uiHandler.postDelayed(this, 1_000L);
            }
        }
    };
    private final Player.Listener audioPlayerListener = new Player.Listener() {
        @Override public void onEvents(Player player, Player.Events events) {
            syncAudioPlaybackState(player, null);
        }

        @Override public void onPlayerError(PlaybackException error) {
            syncAudioPlaybackState(audioController, "Не удалось воспроизвести рассказ");
        }
    };

    @Override public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        restoredCamera = savedInstanceState != null;
        routeViewModel = new ViewModelProvider(this).get(RouteViewModel.class);
        latestUserLat = getIntent().getDoubleExtra(EXTRA_USER_LAT, Double.NaN);
        latestUserLon = getIntent().getDoubleExtra(EXTRA_USER_LON, Double.NaN);

        CoordinatorLayout root = new CoordinatorLayout(this);
        boolean compact = getResources().getConfiguration().screenHeightDp <= 720;
        compactScreen = compact;

        mapContainer = new FrameLayout(this);
        mapContainer.setBackground(UiKit.rounded(UiKit.MAP, 0, this));
        root.addView(mapContainer, new CoordinatorLayout.LayoutParams(-1, -1));
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
        routeSheetView = sheet;
        sheet.setOrientation(LinearLayout.VERTICAL);
        sheet.setPadding(UiKit.dp(this, 16), UiKit.dp(this, compact ? 6 : 7),
                UiKit.dp(this, 16), UiKit.dp(this, 8));
        sheet.setBackground(UiKit.rounded(0xFFFFFFFF, 26, this));
        sheet.setClickable(true);
        sheet.setFocusable(true);
        CoordinatorLayout.LayoutParams sheetParams = new CoordinatorLayout.LayoutParams(-1, -1);
        routeSheetBehavior = new BottomSheetBehavior<>();
        sheetParams.setBehavior(routeSheetBehavior);
        root.addView(sheet, sheetParams);

        FrameLayout dragHandleArea = new FrameLayout(this);
        dragHandleArea.setClickable(true);
        dragHandleArea.setFocusable(true);
        dragHandleArea.setContentDescription("Потяните, чтобы изменить высоту панели");
        TextView handle = UiKit.label(this, "", 1, 0x00000000);
        handle.setBackground(UiKit.rounded(0xFFC7CDCA, 3, this));
        FrameLayout.LayoutParams handleParams = new FrameLayout.LayoutParams(
                UiKit.dp(this, 42), UiKit.dp(this, 5), Gravity.CENTER);
        dragHandleArea.addView(handle, handleParams);
        sheet.addView(dragHandleArea, new LinearLayout.LayoutParams(
                -1, UiKit.dp(this, 48)));

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
        status.setPadding(UiKit.dp(this, 14), UiKit.dp(this, 8),
                UiKit.dp(this, 14), UiKit.dp(this, 8));
        status.setMinHeight(UiKit.dp(this, compact ? 40 : 46));
        status.setBackground(UiKit.rounded(0xFFEAF9EF, 12, this));
        LinearLayout.LayoutParams statusParams = new LinearLayout.LayoutParams(-1, -2);
        statusParams.topMargin = UiKit.dp(this, 4);
        statusParams.bottomMargin = UiKit.dp(this, 4);
        sheet.addView(status, statusParams);

        panelScrollableContent = new LinearLayout(this);
        panelScrollableContent.setOrientation(LinearLayout.VERTICAL);
        pointListScroll = new ScrollView(this);
        pointListScroll.setFillViewport(true);
        pointListScroll.setVerticalScrollBarEnabled(true);
        pointListScroll.setScrollbarFadingEnabled(false);
        pointListScroll.setOverScrollMode(View.OVER_SCROLL_IF_CONTENT_SCROLLS);
        pointListScroll.setNestedScrollingEnabled(true);
        pointListScroll.addView(panelScrollableContent, new ScrollView.LayoutParams(-1, -2));
        sheet.addView(pointListScroll, new LinearLayout.LayoutParams(-1, 0, 1));

        audioCard = new LinearLayout(this);
        audioCard.setOrientation(LinearLayout.VERTICAL);
        audioCard.setPadding(UiKit.dp(this, 14), UiKit.dp(this, 12),
                UiKit.dp(this, 14), UiKit.dp(this, 14));
        audioCard.setBackground(UiKit.bordered(0xFFFFFFFF, 0xFFE1E8E3, 20, this));
        audioCard.setElevation(UiKit.dp(this, 2));
        audioCard.setVisibility(View.GONE);

        audioNewStoryBanner = new LinearLayout(this);
        audioNewStoryBanner.setOrientation(LinearLayout.HORIZONTAL);
        audioNewStoryBanner.setGravity(Gravity.CENTER_VERTICAL);
        audioNewStoryBanner.setPadding(UiKit.dp(this, 10), UiKit.dp(this, 9),
                UiKit.dp(this, 8), UiKit.dp(this, 9));
        audioNewStoryBanner.setBackground(UiKit.rounded(0xFFEAF8EF, 16, this));
        ImageView pendingIcon = new ImageView(this);
        pendingIcon.setImageResource(R.drawable.ic_audio_headphones);
        pendingIcon.setContentDescription(null);
        pendingIcon.setPadding(UiKit.dp(this, 10), UiKit.dp(this, 10),
                UiKit.dp(this, 10), UiKit.dp(this, 10));
        pendingIcon.setBackground(UiKit.rounded(0xFFF5FCF7, 24, this));
        audioNewStoryBanner.addView(pendingIcon, new LinearLayout.LayoutParams(
                UiKit.dp(this, 48), UiKit.dp(this, 48)));
        LinearLayout pendingText = new LinearLayout(this);
        pendingText.setOrientation(LinearLayout.VERTICAL);
        pendingText.setPadding(UiKit.dp(this, 10), 0, UiKit.dp(this, 8), 0);
        TextView pendingLabel = UiKit.label(this, "Доступна новая история!",
                compact ? 14 : 15, UiKit.GREEN_DARK);
        pendingLabel.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        pendingText.addView(pendingLabel, new LinearLayout.LayoutParams(-1, -2));
        audioNewStoryTitle = UiKit.label(this, "", compact ? 15 : 16, UiKit.TEXT);
        audioNewStoryTitle.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        audioNewStoryTitle.setMaxLines(2);
        audioNewStoryTitle.setEllipsize(android.text.TextUtils.TruncateAt.END);
        pendingText.addView(audioNewStoryTitle, new LinearLayout.LayoutParams(-1, -2));
        audioNewStoryBanner.addView(pendingText, new LinearLayout.LayoutParams(0, -2, 1));
        audioNextButton = UiKit.button(this, "▶▶", UiKit.GREEN, 0xFFFFFFFF);
        audioNextButton.setTextSize(compact ? 16 : 18);
        audioNextButton.setContentDescription("Включить новую историю");
        audioNewStoryBanner.addView(audioNextButton, new LinearLayout.LayoutParams(
                UiKit.dp(this, 58), UiKit.dp(this, 52)));
        audioNewStoryBanner.setVisibility(View.GONE);
        LinearLayout.LayoutParams bannerParams = new LinearLayout.LayoutParams(-1, -2);
        bannerParams.bottomMargin = UiKit.dp(this, 10);
        audioCard.addView(audioNewStoryBanner, bannerParams);

        LinearLayout audioHeader = new LinearLayout(this);
        audioHeader.setOrientation(LinearLayout.HORIZONTAL);
        audioHeader.setGravity(Gravity.CENTER_VERTICAL);
        audioStateLabel = UiKit.label(this, "Аудиогид", compact ? 16 : 17,
                UiKit.GREEN_DARK);
        audioStateLabel.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        audioHeader.addView(audioStateLabel, new LinearLayout.LayoutParams(0, -2, 1));
        audioClose = UiKit.label(this, "×", 24, 0xFF77807C);
        audioClose.setGravity(Gravity.CENTER);
        audioClose.setContentDescription("Закрыть аудиогид");
        audioHeader.addView(audioClose, new LinearLayout.LayoutParams(
                UiKit.dp(this, 48), UiKit.dp(this, 48)));
        audioCard.addView(audioHeader, new LinearLayout.LayoutParams(-1, -2));

        LinearLayout audioStoryRow = new LinearLayout(this);
        audioStoryRow.setOrientation(LinearLayout.HORIZONTAL);
        audioStoryRow.setGravity(Gravity.CENTER_VERTICAL);
        audioAvailableIcon = new ImageView(this);
        audioAvailableIcon.setImageResource(R.drawable.ic_audio_headphones);
        audioAvailableIcon.setContentDescription("История аудиогида доступна");
        audioAvailableIcon.setPadding(UiKit.dp(this, 15), UiKit.dp(this, 15),
                UiKit.dp(this, 15), UiKit.dp(this, 15));
        audioAvailableIcon.setBackground(UiKit.rounded(0xFFEAF8EF, 32, this));
        audioStoryRow.addView(audioAvailableIcon, new LinearLayout.LayoutParams(
                UiKit.dp(this, 64), UiKit.dp(this, 64)));
        audioStoryTextContainer = new LinearLayout(this);
        audioStoryTextContainer.setOrientation(LinearLayout.VERTICAL);
        audioStoryTextContainer.setPadding(UiKit.dp(this, 12), 0, 0, 0);
        audioStoryTitle = UiKit.label(this, "", compact ? 18 : 20, UiKit.TEXT);
        audioStoryTitle.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        audioStoryTitle.setMaxLines(2);
        audioStoryTitle.setEllipsize(android.text.TextUtils.TruncateAt.END);
        audioStoryTextContainer.addView(audioStoryTitle,
                new LinearLayout.LayoutParams(-1, -2));
        audioDuration = UiKit.label(this, "", compact ? 14 : 15, UiKit.MUTED);
        LinearLayout.LayoutParams durationParams = new LinearLayout.LayoutParams(-1, -2);
        durationParams.topMargin = UiKit.dp(this, 3);
        audioStoryTextContainer.addView(audioDuration, durationParams);
        audioStoryRow.addView(audioStoryTextContainer,
                new LinearLayout.LayoutParams(0, -2, 1));
        audioCard.addView(audioStoryRow, new LinearLayout.LayoutParams(-1, -2));

        audioListenButton = UiKit.button(this, "Слушать", UiKit.GREEN_DARK, 0xFFFFFFFF);
        audioListenButton.setTextSize(compact ? 16 : 17);
        LinearLayout.LayoutParams listenParams = new LinearLayout.LayoutParams(-1,
                UiKit.dp(this, compact ? 48 : 52));
        listenParams.topMargin = UiKit.dp(this, 12);
        audioCard.addView(audioListenButton, listenParams);

        audioPlayerControls = new LinearLayout(this);
        audioPlayerControls.setOrientation(LinearLayout.VERTICAL);
        audioSeekBar = new SeekBar(this);
        audioSeekBar.setMax(1_000);
        audioSeekBar.setProgressTintList(ColorStateList.valueOf(0xFF079B62));
        audioSeekBar.setProgressBackgroundTintList(ColorStateList.valueOf(0xFFD9DEDB));
        audioSeekBar.setThumbTintList(ColorStateList.valueOf(0xFF079B62));
        audioSeekBar.setContentDescription("Позиция воспроизведения аудиогида");
        audioPlayerControls.addView(audioSeekBar, new LinearLayout.LayoutParams(-1, -2));
        LinearLayout audioTimes = new LinearLayout(this);
        audioTimes.setOrientation(LinearLayout.HORIZONTAL);
        audioElapsed = UiKit.label(this, "0:00", compact ? 13 : 14, UiKit.MUTED);
        audioTotal = UiKit.label(this, "0:00", compact ? 13 : 14, UiKit.MUTED);
        audioTotal.setGravity(Gravity.END);
        audioTimes.addView(audioElapsed, new LinearLayout.LayoutParams(0, -2, 1));
        audioTimes.addView(audioTotal, new LinearLayout.LayoutParams(0, -2, 1));
        audioPlayerControls.addView(audioTimes, new LinearLayout.LayoutParams(-1, -2));
        LinearLayout audioButtons = new LinearLayout(this);
        audioButtons.setOrientation(LinearLayout.HORIZONTAL);
        audioButtons.setGravity(Gravity.CENTER);
        audioRewind = compactAudioButton("↶  −15");
        audioPlayPause = compactAudioButton("▶");
        audioForward = compactAudioButton("↷  +15");
        audioPlayPause.setTextSize(19);
        audioPlayPause.setBackground(UiKit.rounded(0xFFDDF4E5, 15, this));
        audioRewind.setContentDescription("Назад на 15 секунд");
        audioPlayPause.setContentDescription("Воспроизвести или поставить на паузу");
        audioForward.setContentDescription("Вперёд на 15 секунд");
        audioButtons.addView(audioRewind, new LinearLayout.LayoutParams(0,
                UiKit.dp(this, compact ? 48 : 52), 1));
        LinearLayout.LayoutParams playParams = new LinearLayout.LayoutParams(0,
                UiKit.dp(this, compact ? 48 : 52), 1);
        playParams.leftMargin = UiKit.dp(this, 8);
        playParams.rightMargin = UiKit.dp(this, 8);
        audioButtons.addView(audioPlayPause, playParams);
        audioButtons.addView(audioForward, new LinearLayout.LayoutParams(0,
                UiKit.dp(this, compact ? 48 : 52), 1));
        LinearLayout.LayoutParams buttonsParams = new LinearLayout.LayoutParams(-1, -2);
        buttonsParams.topMargin = UiKit.dp(this, 8);
        audioPlayerControls.addView(audioButtons, buttonsParams);
        audioPlayerControls.setVisibility(View.GONE);
        audioCard.addView(audioPlayerControls, new LinearLayout.LayoutParams(-1, -2));
        audioError = UiKit.label(this, "", 12, UiKit.RED);
        audioError.setVisibility(View.GONE);
        audioCard.addView(audioError, new LinearLayout.LayoutParams(-1, -2));
        LinearLayout.LayoutParams audioCardParams = new LinearLayout.LayoutParams(-1, -2);
        audioCardParams.topMargin = UiKit.dp(this, 4);
        audioCardParams.bottomMargin = UiKit.dp(this, 4);
        panelScrollableContent.addView(audioCard, audioCardParams);

        visitingNextCard = new LinearLayout(this);
        visitingNextCard.setOrientation(LinearLayout.HORIZONTAL);
        visitingNextCard.setGravity(Gravity.CENTER_VERTICAL);
        visitingNextCard.setPadding(UiKit.dp(this, 12), UiKit.dp(this, 6),
                UiKit.dp(this, 14), UiKit.dp(this, 6));
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
        nextCardParams.topMargin = UiKit.dp(this, 1);
        nextCardParams.bottomMargin = UiKit.dp(this, 3);
        panelScrollableContent.addView(visitingNextCard, nextCardParams);

        partnerOfferCard = new LinearLayout(this);
        partnerOfferCard.setOrientation(LinearLayout.HORIZONTAL);
        partnerOfferCard.setGravity(Gravity.CENTER_VERTICAL);
        partnerOfferCard.setPadding(UiKit.dp(this, 7), UiKit.dp(this, 7),
                UiKit.dp(this, 7), UiKit.dp(this, 7));
        partnerOfferCard.setBackground(UiKit.bordered(
                0xFFFFFBF4, 0xFFFFC778, 14, this));
        partnerOfferImage = new ImageView(this);
        partnerOfferImage.setScaleType(ImageView.ScaleType.CENTER_CROP);
        partnerOfferImage.setContentDescription("Иллюстрация категории заведения");
        partnerOfferCard.addView(partnerOfferImage, new LinearLayout.LayoutParams(
                UiKit.dp(this, compact ? 58 : 66), UiKit.dp(this, compact ? 58 : 66)));

        LinearLayout partnerText = new LinearLayout(this);
        partnerText.setOrientation(LinearLayout.VERTICAL);
        partnerText.setPadding(UiKit.dp(this, 8), 0, UiKit.dp(this, 6), 0);
        LinearLayout disclosureRow = new LinearLayout(this);
        disclosureRow.setOrientation(LinearLayout.HORIZONTAL);
        disclosureRow.setGravity(Gravity.CENTER_VERTICAL);
        partnerDisclosure = UiKit.label(this, "Рядом по пути", 10, 0xFFD97800);
        partnerDisclosure.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        partnerDisclosure.setPadding(UiKit.dp(this, 7), UiKit.dp(this, 2),
                UiKit.dp(this, 7), UiKit.dp(this, 2));
        partnerDisclosure.setBackground(UiKit.rounded(0xFFFFE9C8, 9, this));
        disclosureRow.addView(partnerDisclosure, new LinearLayout.LayoutParams(-2, -2));
        disclosureRow.addView(new View(this), new LinearLayout.LayoutParams(0, 1, 1));
        partnerOfferDismiss = UiKit.label(this, "×", 17, UiKit.MUTED);
        partnerOfferDismiss.setGravity(Gravity.CENTER);
        partnerOfferDismiss.setContentDescription("Скрыть рекомендацию на этой точке");
        partnerOfferDismiss.setOnClickListener(view -> dismissPartnerOffer());
        disclosureRow.addView(partnerOfferDismiss, new LinearLayout.LayoutParams(
                UiKit.dp(this, 28), UiKit.dp(this, 28)));
        partnerText.addView(disclosureRow, new LinearLayout.LayoutParams(-1, -2));
        partnerOfferView = UiKit.label(this, "", compact ? 14 : 15, UiKit.TEXT);
        partnerOfferView.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        partnerOfferView.setMaxLines(2);
        partnerOfferView.setEllipsize(android.text.TextUtils.TruncateAt.END);
        partnerText.addView(partnerOfferView);
        partnerOfferMeta = UiKit.label(this, "", compact ? 10 : 11, UiKit.MUTED);
        partnerOfferMeta.setSingleLine(true);
        partnerOfferMeta.setEllipsize(android.text.TextUtils.TruncateAt.END);
        partnerText.addView(partnerOfferMeta);
        partnerOfferCard.addView(partnerText, new LinearLayout.LayoutParams(0, -2, 1));
        partnerOfferButton = UiKit.button(
                this, "Добавить в маршрут", UiKit.GREEN_DARK, 0xFFFFFFFF);
        partnerOfferButton.setTextSize(compact ? 10 : 11);
        partnerOfferButton.setMaxLines(2);
        partnerOfferButton.setPadding(UiKit.dp(this, 5), UiKit.dp(this, 5),
                UiKit.dp(this, 5), UiKit.dp(this, 5));
        View.OnClickListener partnerClick = view -> insertPartnerOffer();
        partnerOfferButton.setOnClickListener(partnerClick);
        partnerOfferCard.setOnClickListener(partnerClick);
        partnerOfferCard.setClickable(true);
        partnerOfferCard.addView(partnerOfferButton, new LinearLayout.LayoutParams(
                UiKit.dp(this, compact ? 92 : 106), UiKit.dp(this, compact ? 52 : 58)));
        partnerOfferCard.setVisibility(View.GONE);
        panelScrollableContent.addView(partnerOfferCard, new LinearLayout.LayoutParams(-1, -2));

        pointList = new LinearLayout(this);
        pointList.setOrientation(LinearLayout.VERTICAL);
        panelScrollableContent.addView(pointList, new LinearLayout.LayoutParams(-1, -2));

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
        sheet.bringToFront();
        setContentView(root);
        panelRouteKey = panelRouteKey();
        configureRouteSheet(root);
        setupAudioGuide();

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

    private String panelRouteKey() {
        String routeId = getIntent().getStringExtra(EXTRA_ROUTE_ID);
        return routeId == null ? "unknown" : routeId;
    }

    private void configureRouteSheet(CoordinatorLayout root) {
        if (routeSheetBehavior == null) return;
        routeSheetBehavior.setFitToContents(false);
        routeSheetBehavior.setHalfExpandedRatio(0.60f);
        routeSheetBehavior.setHideable(false);
        routeSheetBehavior.setSkipCollapsed(false);
        routeSheetBehavior.setDraggable(true);
        routeSheetBehavior.addBottomSheetCallback(new BottomSheetBehavior.BottomSheetCallback() {
            @Override public void onStateChanged(@androidx.annotation.NonNull View bottomSheet,
                                                   int newState) {
                if (newState == BottomSheetBehavior.STATE_COLLAPSED
                        || newState == BottomSheetBehavior.STATE_HALF_EXPANDED
                        || newState == BottomSheetBehavior.STATE_EXPANDED) {
                    if (!applyingPanelState) savePanelState(newState);
                }
                updateMapOverlayOffsets(bottomSheet);
            }

            @Override public void onSlide(@androidx.annotation.NonNull View bottomSheet,
                                          float slideOffset) {
                updateMapOverlayOffsets(bottomSheet);
            }
        });
        root.addOnLayoutChangeListener((view, left, top, right, bottom,
                                         oldLeft, oldTop, oldRight, oldBottom) -> {
            int height = bottom - top;
            if (height <= 0) return;
            int collapsedHeight = Math.max(UiKit.dp(this, 132), Math.round(height * 0.20f));
            int expandedOffset = Math.max(0, Math.round(height * 0.02f));
            routeSheetBehavior.setPeekHeight(collapsedHeight, false);
            routeSheetBehavior.setExpandedOffset(expandedOffset);
            if (routeSheetView != null) updateMapOverlayOffsets(routeSheetView);
        });
        root.post(() -> {
            if (root.getHeight() <= 0) return;
            int savedState = getSavedPanelState();
            applyingPanelState = true;
            routeSheetBehavior.setState(savedState);
            applyingPanelState = false;
            if (routeSheetView != null) updateMapOverlayOffsets(routeSheetView);
        });
    }

    private void updateMapOverlayOffsets(View bottomSheet) {
        if (!(bottomSheet.getParent() instanceof View)) return;
        int parentHeight = ((View) bottomSheet.getParent()).getHeight();
        if (parentHeight <= 0) return;
        int visibleSheetHeight = Math.max(0, parentHeight - bottomSheet.getTop());
        float bottomOverlayShift = -visibleSheetHeight;
        if (mapRouteSummary != null) mapRouteSummary.setTranslationY(bottomOverlayShift);
        if (guidancePanel != null) guidancePanel.setTranslationY(bottomOverlayShift);
        if (zoomControls != null) zoomControls.setTranslationY(bottomOverlayShift / 2f);
    }

    private int getSavedPanelState() {
        return getSharedPreferences(ROUTE_LIFECYCLE_PREFERENCES, MODE_PRIVATE)
                .getInt(PANEL_STATE_PREFIX + panelRouteKey,
                        BottomSheetBehavior.STATE_HALF_EXPANDED);
    }

    private void savePanelState(int state) {
        getSharedPreferences(ROUTE_LIFECYCLE_PREFERENCES, MODE_PRIVATE)
                .edit().putInt(PANEL_STATE_PREFIX + panelRouteKey, state).apply();
    }

    private void expandPanelForArrival() {
        if (routeSheetBehavior == null) return;
        routeSheetBehavior.setState(BottomSheetBehavior.STATE_HALF_EXPANDED);
    }

    private Button compactAudioButton(String text) {
        Button button = UiKit.button(this, text, 0xFFEDF8F1, UiKit.GREEN_DARK);
        button.setTextSize(compactScreen ? 14 : 15);
        button.setPadding(UiKit.dp(this, 4), 0, UiKit.dp(this, 4), 0);
        return button;
    }

    private void setupAudioGuide() {
        restoreAudioGuideState();
        audioListenButton.setOnClickListener(view -> {
            audioCoordinator.onUserInteraction(System.currentTimeMillis());
            playAudioStory(audioCoordinator.currentStoryId());
        });
        audioPlayPause.setOnClickListener(view -> {
            audioCoordinator.onUserInteraction(System.currentTimeMillis());
            if (audioController == null) {
                audioLastError = "Плеер подключается. Нажмите ещё раз.";
                connectAudioController();
            } else if (audioCoordinator.playbackState()
                    == AudioGuideCoordinator.PlaybackState.FINISHED) {
                audioController.seekTo(0L);
                audioController.play();
            } else if (audioController.isPlaying()) {
                audioController.pause();
            } else {
                playAudioStory(audioCoordinator.currentStoryId());
            }
            persistAudioGuideState();
            renderAudioGuide();
        });
        audioRewind.setOnClickListener(view -> seekAudioBy(-15_000L));
        audioForward.setOnClickListener(view -> seekAudioBy(15_000L));
        audioClose.setOnClickListener(view -> closeAudioGuide());
        audioNextButton.setOnClickListener(view -> {
            String nextStory = audioCoordinator.switchToPending(System.currentTimeMillis());
            persistAudioGuideState();
            if (nextStory != null) playAudioStory(nextStory);
        });
        audioSeekBar.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            @Override public void onProgressChanged(SeekBar seekBar, int progress,
                                                     boolean fromUser) { }

            @Override public void onStartTrackingTouch(SeekBar seekBar) {
                audioSeekInProgress = true;
                audioCoordinator.onUserInteraction(System.currentTimeMillis());
            }

            @Override public void onStopTrackingTouch(SeekBar seekBar) {
                audioSeekInProgress = false;
                if (audioController != null && audioController.getDuration() > 0L) {
                    long target = audioController.getDuration() * seekBar.getProgress()
                            / seekBar.getMax();
                    audioController.seekTo(target);
                }
                audioCoordinator.onUserInteraction(System.currentTimeMillis());
                persistAudioGuideState();
                renderAudioGuide();
            }
        });
        renderAudioGuide();
    }

    private void connectAudioController() {
        if (audioController != null || audioControllerFuture != null) return;
        SessionToken token = new SessionToken(this,
                new ComponentName(this, AudioPlaybackService.class));
        audioControllerFuture = new MediaController.Builder(this, token).buildAsync();
        ListenableFuture<MediaController> pending = audioControllerFuture;
        pending.addListener(() -> {
            if (audioControllerFuture != pending || isFinishing() || isDestroyed()) return;
            try {
                audioController = pending.get();
                audioController.addListener(audioPlayerListener);
                audioLastError = null;
                syncAudioPlaybackState(audioController, null);
            } catch (Exception error) {
                audioControllerFuture = null;
                audioLastError = "Не удалось подключить аудиоплеер";
                audioCoordinator.onPlayback(audioCoordinator.currentStoryId(),
                        AudioGuideCoordinator.PlaybackState.ERROR);
                persistAudioGuideState();
                renderAudioGuide();
            }
        }, ContextCompat.getMainExecutor(this));
    }

    private void disconnectAudioController() {
        if (audioController != null) audioController.removeListener(audioPlayerListener);
        audioController = null;
        if (audioControllerFuture != null) {
            MediaController.releaseFuture(audioControllerFuture);
            audioControllerFuture = null;
        }
    }

    private void syncAudioPlaybackState(Player player, String errorMessage) {
        if (player == null) return;
        MediaItem item = player.getCurrentMediaItem();
        if (item == null) {
            renderAudioGuide();
            return;
        }
        AudioGuideCoordinator.PlaybackState state;
        if (errorMessage != null || player.getPlayerError() != null) {
            state = AudioGuideCoordinator.PlaybackState.ERROR;
            audioLastError = errorMessage == null
                    ? "Не удалось воспроизвести локальный аудиофайл" : errorMessage;
        } else if (player.getPlaybackState() == Player.STATE_ENDED) {
            state = AudioGuideCoordinator.PlaybackState.FINISHED;
            audioLastError = null;
        } else if (player.isPlaying()) {
            state = AudioGuideCoordinator.PlaybackState.PLAYING;
            audioLastError = null;
        } else if (audioCoordinator.playbackState()
                == AudioGuideCoordinator.PlaybackState.FINISHED
                && (player.getDuration() <= 0L
                || player.getCurrentPosition() >= player.getDuration() - 1_000L)) {
            state = AudioGuideCoordinator.PlaybackState.FINISHED;
            audioLastError = null;
        } else if (player.getCurrentPosition() > 0L
                || audioCoordinator.playbackState()
                != AudioGuideCoordinator.PlaybackState.IDLE) {
            state = AudioGuideCoordinator.PlaybackState.PAUSED;
            audioLastError = null;
        } else {
            state = AudioGuideCoordinator.PlaybackState.IDLE;
        }
        audioCoordinator.onPlayback(item.mediaId, state);
        persistAudioGuideState();
        renderAudioGuide();
    }

    private void playAudioStory(String storyId) {
        AudioStoryCatalog.Story story = AudioStoryCatalog.forCatalogId(storyId);
        if (story == null) return;
        requestAudioNotificationPermission();
        if (audioController == null) {
            audioLastError = "Плеер подключается. Нажмите ещё раз.";
            connectAudioController();
            renderAudioGuide();
            return;
        }
        MediaItem selected = audioController.getCurrentMediaItem();
        if (selected == null || !story.catalogId.equals(selected.mediaId)) {
            audioController.setMediaItem(AudioStoryCatalog.mediaItem(story));
            audioController.prepare();
        } else if (audioController.getPlaybackState() == Player.STATE_ENDED) {
            audioController.seekTo(0L);
        } else if (audioController.getPlaybackState() == Player.STATE_IDLE) {
            audioController.prepare();
        }
        audioLastError = null;
        audioController.play();
    }

    private void requestAudioNotificationPermission() {
        if (android.os.Build.VERSION.SDK_INT >= 33
                && ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS},
                    AUDIO_NOTIFICATION_REQUEST);
        }
    }

    private void seekAudioBy(long deltaMillis) {
        audioCoordinator.onUserInteraction(System.currentTimeMillis());
        if (audioController != null) {
            long duration = audioController.getDuration();
            long upper = duration > 0L ? duration : Long.MAX_VALUE;
            long target = Math.max(0L, Math.min(upper,
                    audioController.getCurrentPosition() + deltaMillis));
            audioController.seekTo(target);
        }
        persistAudioGuideState();
        renderAudioGuide();
    }

    private void closeAudioGuide() {
        audioCoordinator.onUserInteraction(System.currentTimeMillis());
        if (audioController != null) {
            audioController.stop();
            audioController.clearMediaItems();
        }
        audioCoordinator.closeCurrentVisit();
        audioLastError = null;
        persistAudioGuideState();
        renderAudioGuide();
    }

    private void syncAudioGuideForWalk() {
        if (walk == null || route == null || !walk.success) return;
        long now = System.currentTimeMillis();
        boolean visiting = "VISITING".equals(walk.phase)
                && walk.currentPointOrder > 0
                && walk.currentPointOrder <= route.points.size();
        if (!visiting) {
            String previousVisit = audioCoordinator.activeVisitKey();
            if (previousVisit != null) audioCoordinator.onConfirmedExit(previousVisit, now);
            persistAudioGuideState();
            renderAudioGuide();
            return;
        }
        String visitKey = panelRouteKey() + ':' + walk.walkId + ':' + walk.currentPointOrder;
        ApiClient.PlaceOption point = route.points.get(walk.currentPointOrder - 1);
        AudioStoryCatalog.Story story = AudioStoryCatalog.forStablePlaceId(point.placeId);
        if (story == null) {
            audioCoordinator.onVisit(visitKey, null, now);
            persistAudioGuideState();
            renderAudioGuide();
            return;
        }
        AudioStoryCatalog.AvailableStory cached = availableAudioStories.get(story.catalogId);
        if (cached != null) {
            audioCoordinator.onVisit(visitKey, story.catalogId, now);
            persistAudioGuideState();
            renderAudioGuide();
            return;
        }
        int generation = ++audioInspectionGeneration;
        audioIo.execute(() -> {
            AudioStoryCatalog.AvailableStory inspected = AudioStoryCatalog.inspect(this, story);
            runOnUiThread(() -> {
                if (generation != audioInspectionGeneration || isFinishing() || isDestroyed()
                        || walk == null || !"VISITING".equals(walk.phase)
                        || walk.currentPointOrder < 1
                        || walk.currentPointOrder > route.points.size()
                        || !visitKey.equals(panelRouteKey() + ':' + walk.walkId + ':'
                        + walk.currentPointOrder)) return;
                if (inspected != null) {
                    availableAudioStories.put(story.catalogId, inspected);
                    audioCoordinator.onVisit(visitKey, story.catalogId,
                            System.currentTimeMillis());
                }
                persistAudioGuideState();
                renderAudioGuide();
            });
        });
    }

    private void renderAudioGuide() {
        if (audioCard == null) return;
        AudioGuideCoordinator.UiState uiState = audioCoordinator.uiState();
        AudioStoryCatalog.Story story = AudioStoryCatalog.forCatalogId(
                audioCoordinator.currentStoryId());
        if (uiState == AudioGuideCoordinator.UiState.HIDDEN || story == null) {
            audioCard.setVisibility(View.GONE);
            uiHandler.removeCallbacks(audioProgressTick);
            return;
        }
        audioCard.setVisibility(View.VISIBLE);
        audioStoryTitle.setText(story.title);
        long duration = audioDurationMillis(story.catalogId);
        boolean controlsVisible = audioCoordinator.playbackState()
                != AudioGuideCoordinator.PlaybackState.IDLE
                && audioCoordinator.playbackState()
                != AudioGuideCoordinator.PlaybackState.ERROR;
        audioStateLabel.setText(controlsVisible ? "Аудиогид" : "Доступна история!");
        audioAvailableIcon.setVisibility(controlsVisible ? View.GONE : View.VISIBLE);
        audioDuration.setVisibility(controlsVisible ? View.GONE : View.VISIBLE);
        audioDuration.setText("◷  " + formatAudioTime(duration));
        audioStoryTextContainer.setPadding(controlsVisible ? 0 : UiKit.dp(this, 12),
                0, 0, 0);
        audioListenButton.setVisibility(controlsVisible ? View.GONE : View.VISIBLE);
        audioListenButton.setText(audioCoordinator.playbackState()
                == AudioGuideCoordinator.PlaybackState.ERROR ? "Повторить" : "Слушать");
        audioPlayerControls.setVisibility(controlsVisible ? View.VISIBLE : View.GONE);
        audioPlayPause.setText(audioCoordinator.playbackState()
                == AudioGuideCoordinator.PlaybackState.PLAYING ? "Ⅱ" : "▶");
        long position = audioController == null ? 0L : Math.max(0L,
                audioController.getCurrentPosition());
        if (!audioSeekInProgress) {
            audioSeekBar.setProgress(duration > 0L
                    ? (int) Math.min(1_000L, position * 1_000L / duration) : 0);
        }
        audioElapsed.setText(formatAudioTime(position));
        audioTotal.setText(formatAudioTime(duration));
        audioError.setText(audioLastError == null ? "" : audioLastError);
        audioError.setVisibility(audioLastError == null ? View.GONE : View.VISIBLE);
        AudioStoryCatalog.Story pending = AudioStoryCatalog.forCatalogId(
                audioCoordinator.pendingStoryId());
        audioNewStoryBanner.setVisibility(pending == null ? View.GONE : View.VISIBLE);
        if (pending != null) {
            audioNewStoryTitle.setText(pending.title);
        }
        uiHandler.removeCallbacks(audioProgressTick);
        uiHandler.postDelayed(audioProgressTick, 1_000L);
    }

    private long audioDurationMillis(String storyId) {
        if (audioController != null && audioController.getCurrentMediaItem() != null
                && storyId.equals(audioController.getCurrentMediaItem().mediaId)
                && audioController.getDuration() > 0L) {
            return audioController.getDuration();
        }
        AudioStoryCatalog.AvailableStory available = availableAudioStories.get(storyId);
        return available == null ? 0L : available.durationMillis;
    }

    private static String formatAudioTime(long millis) {
        if (millis <= 0L) return "0:00";
        long totalSeconds = millis / 1_000L;
        return String.format(Locale.US, "%d:%02d", totalSeconds / 60, totalSeconds % 60);
    }

    private void expireAudioGuideIfNeeded() {
        if (!audioCoordinator.expireIfNeeded(System.currentTimeMillis())) return;
        if (audioController != null) {
            audioController.stop();
            audioController.clearMediaItems();
        }
        persistAudioGuideState();
        renderAudioGuide();
    }

    private void restoreAudioGuideState() {
        if (audioStateRestored) return;
        audioStateRestored = true;
        SharedPreferences preferences = getSharedPreferences(
                AUDIO_GUIDE_PREFERENCES, MODE_PRIVATE);
        AudioGuideCoordinator.PlaybackState playbackState;
        try {
            playbackState = AudioGuideCoordinator.PlaybackState.valueOf(
                    preferences.getString("playback_state", "IDLE"));
        } catch (IllegalArgumentException error) {
            playbackState = AudioGuideCoordinator.PlaybackState.IDLE;
        }
        audioCoordinator.restore(new AudioGuideCoordinator.Snapshot(
                preferences.getString("current_story", null),
                preferences.getString("pending_story", null),
                preferences.getString("current_story_visit", null),
                preferences.getString("pending_story_visit", null),
                preferences.getString("active_visit", null),
                preferences.getString("active_visit_story", null),
                preferences.getString("dismissed_visit", null),
                preferences.getLong("confirmed_exit_at", -1L),
                preferences.getLong("last_interaction_at", 0L),
                playbackState,
                preferences.getBoolean("hidden", true)));
        expireAudioGuideIfNeeded();
    }

    private void persistAudioGuideState() {
        AudioGuideCoordinator.Snapshot state = audioCoordinator.snapshot();
        getSharedPreferences(AUDIO_GUIDE_PREFERENCES, MODE_PRIVATE).edit()
                .putString("current_story", state.currentStoryId)
                .putString("pending_story", state.pendingStoryId)
                .putString("current_story_visit", state.currentStoryVisitKey)
                .putString("pending_story_visit", state.pendingStoryVisitKey)
                .putString("active_visit", state.activeVisitKey)
                .putString("active_visit_story", state.activeVisitStoryId)
                .putString("dismissed_visit", state.dismissedVisitKey)
                .putLong("confirmed_exit_at", state.confirmedExitAtMillis)
                .putLong("last_interaction_at", state.lastInteractionAtMillis)
                .putString("playback_state", state.playbackState.name())
                .putBoolean("hidden", state.hidden)
                .apply();
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
        updatePointListVisibility();
        pointListScroll.post(() -> pointListScroll.scrollTo(0, 0));
    }

    private void updatePointListVisibility() {
        boolean offerVisible = partnerOfferCard != null
                && partnerOfferCard.getVisibility() == View.VISIBLE;
        boolean visiting = walk != null && "VISITING".equals(walk.phase);
        boolean hasVisiblePoints = !visiting || pointList.getChildCount() > 0;
        pointList.setVisibility(!offerVisible && hasVisiblePoints
                ? View.VISIBLE : View.GONE);
        pointListScroll.setVisibility(View.VISIBLE);
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
        String currentPanelRouteKey = panelRouteKey();
        boolean newArrival = PanelTransition.isNewArrival(
                routeViewModel.observedPanelRouteKey, currentPanelRouteKey,
                routeViewModel.observedWalkPhase, routeViewModel.observedPointOrder,
                walk.phase, walk.currentPointOrder);
        routeViewModel.observedPanelRouteKey = currentPanelRouteKey;
        routeViewModel.observedWalkPhase = walk.phase;
        routeViewModel.observedPointOrder = walk.currentPointOrder;
        if (newArrival) expandPanelForArrival();
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
        syncAudioGuideForWalk();
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
        status.setTextSize(compactScreen ? 27 : 30);
        status.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        status.setGravity(Gravity.START | Gravity.CENTER_VERTICAL);
        status.setIncludeFontPadding(false);
        status.setMinLines(2);
        status.setMaxLines(2);
        status.setLineSpacing(-UiKit.dp(this, 2), 1f);
        int timerHeight = UiKit.dp(this, compactScreen ? 68 : 74);
        status.setMinHeight(timerHeight);
        status.setPadding(UiKit.dp(this, 14), UiKit.dp(this, 2),
                UiKit.dp(this, 16), UiKit.dp(this, 6));
        status.setBackground(UiKit.rounded(0xFFEAF7EE, 16, this));
        status.setTextColor(UiKit.GREEN_DARK);
        status.setCompoundDrawables(makeVisitClockIcon(), null, null, null);
        status.setCompoundDrawablePadding(UiKit.dp(this, 13));
        LinearLayout.LayoutParams timerParams = new LinearLayout.LayoutParams(-1, timerHeight);
        timerParams.topMargin = UiKit.dp(this, 4);
        timerParams.bottomMargin = UiKit.dp(this, 2);
        status.setLayoutParams(timerParams);

        visitingNextCard.setVisibility(model.showNext ? View.VISIBLE : View.GONE);
        visitingNextTitle.setText(model.nextTitle);
        visitingNextMeta.setText(model.nextMeta);
        visitingNextMeta.setVisibility(model.nextMeta.isEmpty() ? View.GONE : View.VISIBLE);
        updatePointListVisibility();
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
            partnerOfferMeta.setText("");
            partnerOfferButton.setText("Добавить в маршрут");
            partnerDisclosure.setText("");
            partnerOfferCard.setVisibility(View.GONE);
            updatePointListVisibility();
            return;
        }
        String venueType = "COFFEE".equals(offer.category) ? "Кофейня" : "Ресторан";
        partnerOfferView.setText(offer.title);
        partnerOfferMeta.setText(venueType + " «" + offer.venueName + "» · "
                + offer.walkingMinutes + " мин пешком");
        partnerDisclosure.setText(offer.disclosure);
        partnerOfferButton.setText(offer.actionLabel);
        partnerOfferImage.setImageResource("COFFEE".equals(offer.category)
                ? R.drawable.recommendation_coffee : R.drawable.recommendation_restaurant);
        partnerOfferCard.setVisibility(View.VISIBLE);
        updatePointListVisibility();
    }

    private void syncPartnerOffer() {
        if (walk == null || !PartnerOfferRequestPolicy.eligible(
                walk.status, walk.phase, walk.currentPointOrder)) {
            invalidatePartnerOffer();
            return;
        }
        String key = PartnerOfferRequestPolicy.key(walk.walkId, walk.currentPointOrder);
        long nowElapsed = SystemClock.elapsedRealtime();
        if (!PartnerOfferRequestPolicy.shouldRequest(
                key, routeViewModel.partnerOfferKey,
                routeViewModel.partnerOffer != null, nowElapsed,
                routeViewModel.partnerOfferLastRequestElapsedMillis)) {
            renderPartnerOffer(VisitingPresentation.PartnerOffer.from(
                    routeViewModel.partnerOffer));
            return;
        }
        routeViewModel.partnerOfferKey = key;
        routeViewModel.partnerOfferLastRequestElapsedMillis = nowElapsed;
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
                routeViewModel.partnerOfferLastStatus = finalResponse.status;
                renderPartnerOffer(VisitingPresentation.PartnerOffer.from(
                        routeViewModel.partnerOffer));
            });
        });
    }

    private void invalidatePartnerOffer() {
        partnerOfferRequestGeneration++;
        routeViewModel.partnerOfferKey = null;
        routeViewModel.partnerOfferLastRequestElapsedMillis = 0L;
        routeViewModel.partnerOfferLastStatus = null;
        routeViewModel.partnerOffer = null;
        renderPartnerOffer(null);
    }

    private void insertPartnerOffer() {
        VisitingPresentation.PartnerOffer offer = VisitingPresentation.PartnerOffer.from(
                routeViewModel.partnerOffer);
        if (partnerOfferInsertInFlight || route == null || walk == null
                || !VisitingPresentation.shouldShowPartnerOffer(offer)) return;
        ApiClient.PartnerOffer selected = routeViewModel.partnerOffer;
        partnerOfferInsertInFlight = true;
        partnerOfferRequestGeneration++;
        partnerOfferCard.setEnabled(false);
        partnerOfferButton.setEnabled(false);
        partnerOfferButton.setText("Добавляем…");
        int baseVersion = route.routeVersion;
        int pointOrder = walk.currentPointOrder;
        String walkId = walk.walkId;
        String cityId = getIntent().getStringExtra(EXTRA_CITY_ID);
        String sessionId = getIntent().getStringExtra(EXTRA_SESSION_ID);
        network.execute(() -> {
            ApiClient.SuggestedPlaceResult response;
            try {
                response = ApiClient.insertSuggestedPlace(
                        walkId, baseVersion, cityId, selected, sessionId);
            } catch (Exception error) {
                response = new ApiClient.SuggestedPlaceResult(false,
                        "Не удалось добавить заведение. Маршрут не изменён.",
                        null, null, null);
            }
            ApiClient.SuggestedPlaceResult finalResponse = response;
            runOnUiThread(() -> {
                partnerOfferInsertInFlight = false;
                if (isFinishing() || isDestroyed()) return;
                partnerOfferCard.setEnabled(true);
                partnerOfferButton.setEnabled(true);
                if (!finalResponse.success) {
                    partnerOfferButton.setText(offer.actionLabel);
                    Toast.makeText(this, finalResponse.message, Toast.LENGTH_LONG).show();
                    if ("VERSION_CONFLICT".equals(finalResponse.errorCode)) loadRoute();
                    return;
                }
                getIntent().putExtra(EXTRA_ROUTE_VERSION,
                        finalResponse.route.routeVersion);
                getIntent().putExtra(EXTRA_ROUTE_SNAPSHOT,
                        ApiClient.routeSnapshot(finalResponse.route));
                boolean sameState = walk != null && walkId.equals(walk.walkId)
                        && pointOrder == walk.currentPointOrder
                        && baseVersion == route.routeVersion
                        && "ACTIVE".equals(walk.status)
                        && "VISITING".equals(walk.phase);
                if (!sameState) {
                    loadRoute();
                    return;
                }
                route = finalResponse.route;
                walk = finalResponse.walk;
                routeViewModel.route = route;
                routeViewModel.walk = walk;
                renderedVisitingStructureKey = null;
                partnerOfferRequestGeneration++;
                routeViewModel.partnerOffer = null;
                routeViewModel.partnerOfferKey = PartnerOfferRequestPolicy.key(
                        walk.walkId, walk.currentPointOrder);
                routeViewModel.partnerOfferLastRequestElapsedMillis =
                        SystemClock.elapsedRealtime();
                routeViewModel.partnerOfferLastStatus = "INSERTED";
                renderPartnerOffer(null);
                showWalkStatus();
                renderRoute(true);
                syncLocationTracking();
                Toast.makeText(this, "Заведение добавлено в маршрут",
                        Toast.LENGTH_SHORT).show();
            });
        });
    }

    private void dismissPartnerOffer() {
        VisitingPresentation.PartnerOffer offer = VisitingPresentation.PartnerOffer.from(
                routeViewModel.partnerOffer);
        if (partnerOfferInsertInFlight || walk == null
                || !VisitingPresentation.shouldShowPartnerOffer(offer)) return;
        partnerOfferInsertInFlight = true;
        partnerOfferRequestGeneration++;
        partnerOfferCard.setEnabled(false);
        partnerOfferButton.setEnabled(false);
        partnerOfferDismiss.setEnabled(false);
        String walkId = walk.walkId;
        int pointOrder = walk.currentPointOrder;
        String sessionId = getIntent().getStringExtra(EXTRA_SESSION_ID);
        network.execute(() -> {
            boolean dismissed;
            try {
                dismissed = ApiClient.dismissPartnerOffer(walkId, sessionId);
            } catch (Exception error) {
                dismissed = false;
            }
            boolean finalDismissed = dismissed;
            runOnUiThread(() -> {
                partnerOfferInsertInFlight = false;
                if (isFinishing() || isDestroyed()) return;
                partnerOfferCard.setEnabled(true);
                partnerOfferButton.setEnabled(true);
                partnerOfferDismiss.setEnabled(true);
                if (!finalDismissed) {
                    Toast.makeText(this, "Не удалось скрыть рекомендацию. Попробуйте ещё раз.",
                            Toast.LENGTH_LONG).show();
                    return;
                }
                if (walk != null && walkId.equals(walk.walkId)
                        && pointOrder == walk.currentPointOrder) {
                    routeViewModel.partnerOffer = null;
                    routeViewModel.partnerOfferKey = PartnerOfferRequestPolicy.key(
                            walk.walkId, walk.currentPointOrder);
                    routeViewModel.partnerOfferLastRequestElapsedMillis =
                            SystemClock.elapsedRealtime();
                    routeViewModel.partnerOfferLastStatus = "DISMISSED";
                    renderPartnerOffer(null);
                }
            });
        });
    }

    private void resetVisitingUi() {
        renderedVisitingStructureKey = null;
        visitingNextCard.setVisibility(View.GONE);
        pointListScroll.setVisibility(View.VISIBLE);
        pointList.setVisibility(View.VISIBLE);
        invalidatePartnerOffer();
        nextLabel.setText("ПЕРВАЯ ТОЧКА");
        status.setTextSize(14);
        status.setTypeface(Typeface.DEFAULT, Typeface.NORMAL);
        status.setTextColor(UiKit.MUTED);
        status.setGravity(Gravity.CENTER_VERTICAL);
        status.setIncludeFontPadding(true);
        status.setMinLines(0);
        status.setMaxLines(Integer.MAX_VALUE);
        status.setMinHeight(UiKit.dp(this, compactScreen ? 40 : 46));
        status.setPadding(UiKit.dp(this, 14), UiKit.dp(this, 8),
                UiKit.dp(this, 14), UiKit.dp(this, 8));
        status.setBackground(UiKit.rounded(0xFFEAF9EF, 12, this));
        status.setCompoundDrawables(null, null, null, null);
        status.setCompoundDrawablePadding(0);
        LinearLayout.LayoutParams statusParams = new LinearLayout.LayoutParams(-1, -2);
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
        connectAudioController();
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
        disconnectAudioController();
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
        audioIo.shutdownNow();
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
        long partnerOfferLastRequestElapsedMillis;
        String partnerOfferLastStatus;
        ApiClient.PartnerOffer partnerOffer;
        String observedPanelRouteKey;
        String observedWalkPhase;
        int observedPointOrder;
    }
}
