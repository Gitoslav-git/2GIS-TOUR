package ru.gulyay.app;

import android.Manifest;
import android.content.Intent;
import android.app.AlertDialog;
import android.content.pm.PackageManager;
import android.location.Location;
import android.location.LocationListener;
import android.location.LocationManager;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.View;
import android.view.inputmethod.InputMethodManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import androidx.activity.ComponentActivity;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** A deliberately small, route-only chat surface. It never renders a second map. */
public final class RouteChatActivity extends ComponentActivity {
    static final String EXTRA_CITY = "city";
    static final String EXTRA_QUERY = "query";
    static final String EXTRA_SESSION = "session";
    static final String EXTRA_ROUTE_ID = "routeId";
    static final String EXTRA_ROUTE_VERSION = "routeVersion";
    static final String EXTRA_SNAPSHOT = "routeSnapshot";
    static final String EXTRA_OPEN_ROUTE = "openRoute";
    static final String EXTRA_RESET_ROUTE = "resetRoute";
    static final String EXTRA_START_LAT = "startLat";
    static final String EXTRA_START_LON = "startLon";
    static final String EXTRA_START_ACCURACY = "startAccuracyMeters";
    static final String EXTRA_START_MEASURED_AT = "startMeasuredAtMillis";
    static final String EXTRA_FILTERS_JSON = "filtersJson";
    private static final int LOCATION_PERMISSION_REQUEST = 78;
    private static final long LOCATION_TIMEOUT_MILLIS = 20_000L;
    private final ExecutorService network = Executors.newSingleThreadExecutor();
    private LinearLayout messages; private ScrollView scroll; private EditText input; private Button send;
    private final Handler typingHandler = new Handler(Looper.getMainLooper());
    private TextView typingBubble; private Button currentAction;
    private int typingFrame;
    private String city, session, routeId, initialRouteId; private int routeVersion; private boolean busy; private ApiClient.Result latest; private boolean editingExistingRoute, createdNewRouteInThisChat;
    private RouteStartLocation startLocation;
    private LocationManager locationManager;
    private LocationListener locationListener;
    private Runnable locationTimeout;
    private String pendingNewRouteQuery;
    private RouteChatFilters routeFilters;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        city = getIntent().getStringExtra(EXTRA_CITY); session = getIntent().getStringExtra(EXTRA_SESSION);
        routeFilters = RouteChatFilters.fromExtra(
                getIntent().getStringExtra(EXTRA_FILTERS_JSON));
        if (getIntent().hasExtra(EXTRA_START_LAT) && getIntent().hasExtra(EXTRA_START_LON)) {
            startLocation = new RouteStartLocation(
                    getIntent().getDoubleExtra(EXTRA_START_LAT, 0.0),
                    getIntent().getDoubleExtra(EXTRA_START_LON, 0.0),
                    getIntent().getDoubleExtra(EXTRA_START_ACCURACY, Double.MAX_VALUE),
                    getIntent().getLongExtra(EXTRA_START_MEASURED_AT, 0L));
        }
        routeId = getIntent().getStringExtra(EXTRA_ROUTE_ID); initialRouteId = routeId; editingExistingRoute = initialRouteId != null; routeVersion = getIntent().getIntExtra(EXTRA_ROUTE_VERSION, 0);
        LinearLayout root = new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL); root.setPadding(UiKit.dp(this,16), UiKit.dp(this,18), UiKit.dp(this,16), UiKit.dp(this,12)); root.setBackgroundColor(0xFFFFFFFF);
        LinearLayout header = new LinearLayout(this); header.setGravity(Gravity.CENTER_VERTICAL);
        Button back=UiKit.button(this,"‹",UiKit.SOFT,UiKit.TEXT); back.setTextSize(28); header.addView(back,new LinearLayout.LayoutParams(UiKit.dp(this,52),UiKit.dp(this,52)));
        TextView title=UiKit.label(this,"✦  Гуляй\nМаршрут под настроение",22,UiKit.TEXT); title.setPadding(UiKit.dp(this,12),0,0,0); header.addView(title,new LinearLayout.LayoutParams(0,-2,1)); Button fresh=null; if(!editingExistingRoute){ fresh=UiKit.button(this,"Отмена",UiKit.RED,0xFFFFFFFF); fresh.setContentDescription("Закрыть создание маршрута"); header.addView(fresh,new LinearLayout.LayoutParams(UiKit.dp(this,88),UiKit.dp(this,48))); } root.addView(header);
        scroll=new ScrollView(this); messages=new LinearLayout(this); messages.setOrientation(LinearLayout.VERTICAL); scroll.addView(messages); root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        LinearLayout composer=new LinearLayout(this); composer.setGravity(Gravity.CENTER_VERTICAL); input=new EditText(this); input.setHint("Напишите, что изменить…"); input.setMinLines(1); input.setMaxLines(4); input.setBackground(UiKit.bordered(0xFFFFFFFF,0xFFE0E6E1,24,this)); composer.addView(input,new LinearLayout.LayoutParams(0,-2,1)); send=UiKit.button(this,"➤",UiKit.GREEN,0xFFFFFFFF); composer.addView(send,new LinearLayout.LayoutParams(UiKit.dp(this,58),UiKit.dp(this,52))); root.addView(composer);
        setContentView(root); back.setOnClickListener(v->onBackPressed()); if(fresh!=null) fresh.setOnClickListener(v->confirmCancelCreate()); send.setOnClickListener(v->submit());
        String first=getIntent().getStringExtra(EXTRA_QUERY);
        if (routeId == null && first != null && !first.trim().isEmpty()) {
            user(first);
            requestInitial(first);
        } else if (routeId != null && routeFilters != null
                && first != null && !first.trim().isEmpty()) {
            user(first);
            loading(true);
            network.execute(() -> call(() -> ApiClient.reviseRoute(
                    routeId, routeVersion, city, first, session,
                    startLocation == null ? null : startLocation.lat,
                    startLocation == null ? null : startLocation.lon,
                    startLocation == null ? null : startLocation.accuracyMeters,
                    routeFilters.copyJson())));
        } else bot("Что хотите изменить в маршруте?");
    }
    private void user(String text){ bubble(text,false); }
    private void bot(String text){ bubble(text,true); }
    private void bubble(String text, boolean bot){ TextView v=UiKit.label(this,text,17,UiKit.TEXT); v.setLineSpacing(0,1.1f); v.setPadding(UiKit.dp(this,16),UiKit.dp(this,12),UiKit.dp(this,16),UiKit.dp(this,12)); v.setBackground(UiKit.rounded(bot?0xFFE8F8ED:0xFFF1F2F3,22,this)); LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-2,-2); p.gravity=bot?Gravity.START:Gravity.END; p.topMargin=UiKit.dp(this,8); messages.addView(v,p); scroll.post(()->scroll.fullScroll(View.FOCUS_DOWN)); }
    private final Runnable typingTick = new Runnable(){ @Override public void run(){ if(typingBubble==null)return; String[] dots={"● ○ ○","○ ● ○","○ ○ ●"}; typingBubble.setText("Гуляй составляет маршрут…\n"+dots[typingFrame++%dots.length]); typingHandler.postDelayed(this,360); }};
    private void loading(boolean on){ busy=on; input.setEnabled(!on); send.setEnabled(!on); if(on){ removeTyping(); typingBubble=UiKit.label(this,"",17,UiKit.TEXT); typingBubble.setPadding(UiKit.dp(this,16),UiKit.dp(this,12),UiKit.dp(this,16),UiKit.dp(this,12)); typingBubble.setBackground(UiKit.rounded(0xFFE8F8ED,22,this)); LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-2,-2); p.gravity=Gravity.START; p.topMargin=UiKit.dp(this,8); messages.addView(typingBubble,p); typingFrame=0; typingHandler.post(typingTick); scroll.post(()->scroll.fullScroll(View.FOCUS_DOWN)); } else removeTyping(); }
    private void removeTyping(){ typingHandler.removeCallbacks(typingTick); if(typingBubble!=null){ messages.removeView(typingBubble); typingBubble=null; } }
    private void requestInitial(String query){ requestNewRoute(query); }
    private void submit(){ String text=input.getText().toString().trim(); if(busy||text.length()<2)return; input.setText(""); user(text); if(routeId==null) requestNewRoute(text); else { loading(true); network.execute(()->call(()->ApiClient.chatRevision(routeId,routeVersion,city,text,session))); } }

    private void requestNewRoute(String query) {
        if (busy) return;
        pendingNewRouteQuery = query;
        loading(true);
        if (startLocation != null && startLocation.isFreshAndAccurate(System.currentTimeMillis())) {
            createNewRoute(query, startLocation);
            return;
        }
        requestFreshLocation();
    }

    private void createNewRoute(String query, RouteStartLocation location) {
        pendingNewRouteQuery = null;
        network.execute(() -> call(() -> ApiClient.createRoute(
                city, query, session,
                location == null ? null : location.lat,
                location == null ? null : location.lon,
                location == null ? null : location.accuracyMeters,
                routeFilters == null ? null : routeFilters.copyJson())));
    }

    private void requestFreshLocation() {
        if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED
                && checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.ACCESS_FINE_LOCATION,
                    Manifest.permission.ACCESS_COARSE_LOCATION}, LOCATION_PERMISSION_REQUEST);
            return;
        }
        locationManager = (LocationManager) getSystemService(LOCATION_SERVICE);
        boolean gps = locationManager.isProviderEnabled(LocationManager.GPS_PROVIDER);
        boolean networkProvider = locationManager.isProviderEnabled(LocationManager.NETWORK_PROVIDER);
        if (!gps && !networkProvider) { showLocationFallback("Геопозиция выключена."); return; }
        Location cached = bestLastKnown(gps, networkProvider);
        if (cached != null) {
            RouteStartLocation candidate = fromLocation(cached);
            if (candidate.isFreshAndAccurate(System.currentTimeMillis())
                    && MainActivity.locationMatchesCity(city, candidate.lat, candidate.lon)) {
                startLocation = candidate;
                createNewRoute(pendingNewRouteQuery, candidate);
                return;
            }
        }
        if (!claimGeoAttempt()) {
            showLocationFallback("Лимит определения геопозиции достигнут. Повторите немного позже.");
            return;
        }
        locationListener = location -> {
            RouteStartLocation candidate = fromLocation(location);
            if (!candidate.isFreshAndAccurate(System.currentTimeMillis())
                    || !MainActivity.locationMatchesCity(city, candidate.lat, candidate.lon)) return;
            stopLocationRequest();
            startLocation = candidate;
            createNewRoute(pendingNewRouteQuery, candidate);
        };
        try {
            locationManager.requestSingleUpdate(gps ? LocationManager.GPS_PROVIDER
                    : LocationManager.NETWORK_PROVIDER, locationListener, Looper.getMainLooper());
            locationTimeout = () -> { stopLocationRequest(); showLocationFallback(
                    "Не удалось получить свежую геопозицию."); };
            typingHandler.postDelayed(locationTimeout, LOCATION_TIMEOUT_MILLIS);
        } catch (SecurityException error) {
            stopLocationRequest();
            showLocationFallback("Нет разрешения на геопозицию.");
        }
    }

    private Location bestLastKnown(boolean gps, boolean networkProvider) {
        Location best = null;
        try {
            if (gps) best = locationManager.getLastKnownLocation(LocationManager.GPS_PROVIDER);
            if (networkProvider) {
                Location other = locationManager.getLastKnownLocation(LocationManager.NETWORK_PROVIDER);
                if (other != null && (best == null || other.getTime() > best.getTime())) best = other;
            }
        } catch (SecurityException ignored) { }
        return best;
    }

    private static RouteStartLocation fromLocation(Location location) {
        return new RouteStartLocation(location.getLatitude(), location.getLongitude(),
                location.hasAccuracy() ? location.getAccuracy() : Double.MAX_VALUE,
                location.getTime());
    }

    private boolean claimGeoAttempt() {
        long now = System.currentTimeMillis();
        android.content.SharedPreferences prefs = getSharedPreferences("geo_attempt_throttle", MODE_PRIVATE);
        long previous = prefs.getLong("previous", 0L), latestAttempt = prefs.getLong("latest", 0L);
        long cutoff = now - 60_000L;
        if (previous > now || latestAttempt > now) { previous = 0L; latestAttempt = 0L; }
        if (previous > cutoff) return false;
        if (latestAttempt > cutoff) previous = latestAttempt; else previous = 0L;
        prefs.edit().putLong("previous", previous).putLong("latest", now).apply();
        return true;
    }

    private void showLocationFallback(String reason) {
        stopLocationRequest();
        loading(false);
        new AlertDialog.Builder(this).setTitle("Точное местоположение не определено")
                .setMessage(reason + " Можно повторить определение GPS или явно построить маршрут от центра выбранного города.")
                .setNegativeButton("Повторить GPS", (d, w) -> { loading(true); requestFreshLocation(); })
                .setPositiveButton("От центра города", (d, w) -> { loading(true); createNewRoute(pendingNewRouteQuery, null); })
                .setOnCancelListener(d -> pendingNewRouteQuery = null).show();
    }

    private void stopLocationRequest() {
        if (locationTimeout != null) { typingHandler.removeCallbacks(locationTimeout); locationTimeout = null; }
        if (locationManager != null && locationListener != null) {
            try { locationManager.removeUpdates(locationListener); } catch (SecurityException ignored) { }
        }
        locationListener = null;
    }

    @Override public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(requestCode, permissions, results);
        if (requestCode != LOCATION_PERMISSION_REQUEST) return;
        boolean granted = false;
        for (int result : results) granted |= result == PackageManager.PERMISSION_GRANTED;
        if (granted) requestFreshLocation(); else showLocationFallback("Нет разрешения на геопозицию.");
    }
    private interface Call { ApiClient.Result run() throws Exception; }
    private void call(Call work){ ApiClient.Result result; try { result=work.run(); } catch(Exception e){ result=new ApiClient.Result(false,"Не удалось связаться с сервером. Попробуйте ещё раз.",null,0); } ApiClient.Result r=result; runOnUiThread(()->finishCall(r)); }
    private void finishCall(ApiClient.Result r){ loading(false); if(!r.success){ bot(r.message); return; } latest=r; createdNewRouteInThisChat = !editingExistingRoute; routeId=r.routeId; routeVersion=r.routeVersion; StringBuilder s=new StringBuilder("Готово! Маршрут примерно на ").append(r.totalMinutes>0?r.totalMinutes:"несколько").append(" мин.\n\n"); for(int i=0;i<r.points.size();i++)s.append(i+1).append(". ").append(r.points.get(i).name).append('\n'); bot(s.toString().trim()); if(currentAction!=null) messages.removeView(currentAction); currentAction=UiKit.button(this,editingExistingRoute?"Применить изменения":"▶  Начать маршрут",UiKit.GREEN,0xFFFFFFFF); currentAction.setOnClickListener(v->returnRoute(true)); messages.addView(currentAction,new LinearLayout.LayoutParams(-1,UiKit.dp(this,54))); scroll.post(()->scroll.fullScroll(View.FOCUS_DOWN)); }
    private void returnRoute(boolean open){ if(latest!=null){ Intent data=new Intent(); data.putExtra(EXTRA_CITY,city); data.putExtra(EXTRA_SESSION,session); data.putExtra(EXTRA_ROUTE_ID,routeId); data.putExtra(EXTRA_ROUTE_VERSION,routeVersion); data.putExtra(EXTRA_SNAPSHOT,ApiClient.routeSnapshot(latest)); data.putExtra(EXTRA_QUERY,getIntent().getStringExtra(EXTRA_QUERY)); data.putExtra(EXTRA_OPEN_ROUTE,open); setResult(RESULT_OK,data); } finish(); }
    private void confirmCancelCreate(){ if(busy)return; new AlertDialog.Builder(this).setTitle("Отменить создание маршрута?").setMessage(createdNewRouteInThisChat ? "Созданный маршрут будет удалён." : "Чат будет закрыт без создания маршрута.").setNegativeButton("Продолжить",null).setPositiveButton("Подтвердить",(d,w)->cancelCreateChat()).show(); }
    private void cancelCreateChat(){ if(!createdNewRouteInThisChat || routeId==null){ setResult(RESULT_CANCELED); finish(); return; } loading(true); network.execute(()->{ boolean deleted; try{ deleted=ApiClient.deleteRoute(routeId,session).success; }catch(Exception ignored){ deleted=false; } final boolean done=deleted; runOnUiThread(()->{ loading(false); if(!done){ bot("Не удалось отменить маршрут. Попробуйте ещё раз."); return; } Intent data=new Intent(); data.putExtra(EXTRA_RESET_ROUTE,true); setResult(RESULT_OK,data); finish(); }); }); }
    @Override public void onBackPressed(){ if(editingExistingRoute){ if(latest!=null)returnRoute(false); else { setResult(RESULT_CANCELED); finish(); } } else if(!busy) confirmCancelCreate(); }
    @Override protected void onDestroy(){ stopLocationRequest(); removeTyping(); network.shutdownNow(); super.onDestroy(); }
}
