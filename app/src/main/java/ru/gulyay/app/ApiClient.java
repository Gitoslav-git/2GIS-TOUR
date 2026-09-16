package ru.gulyay.app;

import org.json.JSONArray;
import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.UUID;

final class ApiClient {
    private ApiClient() { }

    static final class PlaceOption {
        final String placeId;
        final String name;
        final boolean food;
        final double lat;
        final double lon;

        PlaceOption(String placeId, String name, boolean food) {
            this(placeId, name, food, Double.NaN, Double.NaN);
        }

        PlaceOption(String placeId, String name, boolean food, double lat, double lon) {
            this.placeId = placeId;
            this.name = name;
            this.food = food;
            this.lat = lat;
            this.lon = lon;
        }

        @Override public String toString() {
            return food ? name + " (еда)" : name;
        }
    }

    static final class GeoCoordinate {
        final double lat;
        final double lon;

        GeoCoordinate(double lat, double lon) {
            this.lat = lat;
            this.lon = lon;
        }
    }

    static final class Result {
        final boolean success;
        final String message;
        final String routeId;
        final int routeVersion;
        final int retryAfterSeconds;
        final String errorCode;
        final List<PlaceOption> points;
        final List<GeoCoordinate> path;

        Result(boolean success, String message, String routeId, int routeVersion) {
            this(success, message, routeId, routeVersion, 0, null,
                    Collections.emptyList());
        }

        Result(boolean success, String message, String routeId, int routeVersion,
               int retryAfterSeconds, String errorCode) {
            this(success, message, routeId, routeVersion, retryAfterSeconds, errorCode,
                    Collections.emptyList());
        }

        Result(boolean success, String message, String routeId, int routeVersion,
               int retryAfterSeconds, String errorCode, List<PlaceOption> points) {
            this(success, message, routeId, routeVersion, retryAfterSeconds, errorCode,
                    points, Collections.emptyList());
        }

        Result(boolean success, String message, String routeId, int routeVersion,
               int retryAfterSeconds, String errorCode, List<PlaceOption> points,
               List<GeoCoordinate> path) {
            this.success = success;
            this.message = message;
            this.routeId = routeId;
            this.routeVersion = routeVersion;
            this.retryAfterSeconds = retryAfterSeconds;
            this.errorCode = errorCode;
            this.points = points;
            this.path = path;
        }
    }

    static final class SearchResult {
        final boolean success;
        final String message;
        final int retryAfterSeconds;
        final List<PlaceOption> items;

        SearchResult(boolean success, String message, int retryAfterSeconds,
                     List<PlaceOption> items) {
            this.success = success;
            this.message = message;
            this.retryAfterSeconds = retryAfterSeconds;
            this.items = items;
        }
    }

    static Result createRoute(String cityId, String query, String sessionId) throws Exception {
        return createRoute(cityId, query, sessionId, null, null);
    }

    static Result createRoute(String cityId, String query, String sessionId,
                              Double startLat, Double startLon) throws Exception {
        return createRoute(cityId, query, sessionId, startLat, startLon, 100.0);
    }

    static Result createRoute(String cityId, String query, String sessionId,
                              Double startLat, Double startLon,
                              Double accuracyMeters) throws Exception {
        JSONObject payload = new JSONObject();
        payload.put("cityId", cityId);
        payload.put("query", query);
        payload.put("deviceSessionId", sessionId);
        payload.put("filters", new JSONObject());
        if (startLat != null && startLon != null) {
            JSONObject location = new JSONObject();
            location.put("lat", startLat);
            location.put("lon", startLon);
            location.put("accuracyMeters", accuracyMeters == null
                    ? 100.0 : Math.max(0.0, accuracyMeters));
            payload.put("startLocation", location);
        }
        return send("/v1/routes", payload, sessionId, cityId);
    }

    static Result reviseRoute(String routeId, int baseVersion, String cityId,
                              String query, String sessionId) throws Exception {
        return reviseRoute(routeId, baseVersion, cityId, query, sessionId, null, null);
    }

    static Result reviseRoute(String routeId, int baseVersion, String cityId,
                              String query, String sessionId,
                              Double startLat, Double startLon) throws Exception {
        return reviseRoute(routeId, baseVersion, cityId, query, sessionId,
                startLat, startLon, 100.0);
    }

    static Result reviseRoute(String routeId, int baseVersion, String cityId,
                              String query, String sessionId,
                              Double startLat, Double startLon,
                              Double accuracyMeters) throws Exception {
        JSONObject payload = new JSONObject();
        payload.put("baseVersion", baseVersion);
        payload.put("mode", "CHANGE_QUERY");
        payload.put("query", query);
        Result revised = send("/v1/routes/" + routeId + "/revisions", payload, sessionId, cityId);
        if (!revised.success && "NOT_FOUND".equals(revised.errorCode)) {
            Result recreated = createRoute(cityId, query, sessionId, startLat, startLon,
                    accuracyMeters);
            if (recreated.success) {
                return new Result(true, "Старый маршрут отсутствовал на сервере — построен новый.\n\n" +
                        recreated.message, recreated.routeId, recreated.routeVersion,
                        0, null, recreated.points, recreated.path);
            }
            return recreated;
        }
        return revised;
    }

    static Result revisePoints(String routeId, int baseVersion, String cityId,
                               List<PlaceOption> points, String sessionId) throws Exception {
        JSONObject payload = new JSONObject();
        payload.put("baseVersion", baseVersion);
        payload.put("mode", "EDIT_POINTS");
        JSONArray ids = new JSONArray();
        for (PlaceOption point : points) ids.put(point.placeId);
        payload.put("pointIds", ids);
        return send("/v1/routes/" + routeId + "/revisions", payload, sessionId, cityId);
    }

    static Result getRoute(String routeId, String cityId, String sessionId) throws Exception {
        return getRouteResponse("/v1/routes/" + routeId, sessionId, cityId);
    }

    static SearchResult searchPlaces(String cityId, String query, String sessionId) throws Exception {
        if (BuildConfig.BACKEND_BASE_URL.equals("https://example.invalid")) {
            return new SearchResult(false, "Сборка не подключена к backend.", 0,
                    Collections.emptyList());
        }
        String encoded = URLEncoder.encode(query, StandardCharsets.UTF_8.name());
        HttpURLConnection connection = open("/v1/places?cityId=" + cityId + "&q=" + encoded,
                "GET", sessionId);
        try {
            int status = connection.getResponseCode();
            JSONObject response = readJson(connection, status);
            if (status >= 400) {
                return searchError(response, status);
            }
            JSONArray items = response.getJSONArray("items");
            List<PlaceOption> places = new ArrayList<>();
            for (int i = 0; i < items.length(); i++) {
                JSONObject item = items.getJSONObject(i);
                places.add(new PlaceOption(item.getString("placeId"), item.getString("name"),
                        item.optBoolean("isFood"), item.getDouble("lat"), item.getDouble("lon")));
            }
            String message = places.isEmpty() ? "Подходящих мест не найдено" :
                    "Найдено мест: " + places.size();
            return new SearchResult(true, message, 0, places);
        } finally {
            connection.disconnect();
        }
    }

    private static Result send(String path, JSONObject payload, String sessionId,
                               String cityId) throws Exception {
        if (BuildConfig.BACKEND_BASE_URL.equals("https://example.invalid")) {
            return new Result(false, "Для построения маршрута нужен адрес запущенного backend. Эта сборка пока не подключена к серверу.", null, 0);
        }
        HttpURLConnection connection = open(path, "POST", sessionId);
        connection.setDoOutput(true);
        connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
        byte[] bytes = payload.toString().getBytes(StandardCharsets.UTF_8);
        try {
            try (java.io.OutputStream output = connection.getOutputStream()) {
                output.write(bytes);
            }
            int status = connection.getResponseCode();
            JSONObject response = readJson(connection, status);
            if (status >= 400) {
                return routeError(response, status);
            }
            return new Result(true, routeSummary(response, cityId), response.getString("routeId"),
                    response.getInt("routeVersion"), 0, null, routePoints(response),
                    routePath(response));
        } finally {
            connection.disconnect();
        }
    }

    private static Result getRouteResponse(String path, String sessionId, String cityId) throws Exception {
        if (BuildConfig.BACKEND_BASE_URL.equals("https://example.invalid")) {
            return new Result(false, "Сборка не подключена к backend.", null, 0);
        }
        HttpURLConnection connection = open(path, "GET", sessionId);
        try {
            int status = connection.getResponseCode();
            JSONObject response = readJson(connection, status);
            if (status >= 400) return routeError(response, status);
            return new Result(true, routeSummary(response, cityId), response.getString("routeId"),
                    response.getInt("routeVersion"), 0, null, routePoints(response),
                    routePath(response));
        } finally {
            connection.disconnect();
        }
    }

    private static HttpURLConnection open(String path, String method, String sessionId)
            throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL(
                BuildConfig.BACKEND_BASE_URL + path).openConnection();
        connection.setRequestMethod(method);
        connection.setConnectTimeout(7000);
        connection.setReadTimeout(60000);
        connection.setRequestProperty("X-Device-Session", sessionId);
        connection.setRequestProperty("X-Request-Id", UUID.randomUUID().toString());
        return connection;
    }

    private static JSONObject readJson(HttpURLConnection connection, int status) throws Exception {
        InputStream stream = status < 400 ? connection.getInputStream() : connection.getErrorStream();
        if (stream == null) throw new IllegalStateException("Backend вернул пустой ответ");
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        byte[] chunk = new byte[4096];
        try (InputStream input = stream) {
            int n;
            while ((n = input.read(chunk)) != -1) buffer.write(chunk, 0, n);
        }
        String body = buffer.toString("UTF-8");
        if (body.trim().isEmpty()) throw new IllegalStateException("Backend вернул пустой ответ");
        return new JSONObject(body);
    }

    private static Result routeError(JSONObject response, int status) {
        JSONObject error = response.optJSONObject("error");
        if (error == null) return new Result(false, "Ошибка сервера (" + status + ")", null, 0);
        JSONObject details = error.optJSONObject("details");
        int retryAfter = details == null ? 0 : details.optInt("retryAfterSeconds", 0);
        String code = error.optString("code");
        return new Result(false, humanError(code, error.optString("message")),
                null, 0, retryAfter, code);
    }

    private static SearchResult searchError(JSONObject response, int status) {
        Result error = routeError(response, status);
        return new SearchResult(false, error.message, error.retryAfterSeconds,
                Collections.emptyList());
    }

    private static List<PlaceOption> routePoints(JSONObject response) throws Exception {
        JSONArray items = response.getJSONArray("points");
        List<PlaceOption> points = new ArrayList<>();
        for (int i = 0; i < items.length(); i++) {
            JSONObject item = items.getJSONObject(i);
            points.add(new PlaceOption(item.getString("placeId"), item.getString("name"),
                    item.optBoolean("isFood"), item.getDouble("lat"), item.getDouble("lon")));
        }
        return points;
    }

    private static List<GeoCoordinate> routePath(JSONObject response) throws Exception {
        JSONArray legs = response.getJSONArray("legs");
        List<GeoCoordinate> path = new ArrayList<>();
        for (int legIndex = 0; legIndex < legs.length(); legIndex++) {
            JSONArray geometry = legs.getJSONObject(legIndex).getJSONArray("geometry");
            for (int pointIndex = 0; pointIndex < geometry.length(); pointIndex++) {
                JSONArray coordinate = geometry.getJSONArray(pointIndex);
                GeoCoordinate next = new GeoCoordinate(coordinate.getDouble(1),
                        coordinate.getDouble(0));
                if (path.isEmpty()) {
                    path.add(next);
                } else {
                    GeoCoordinate previous = path.get(path.size() - 1);
                    if (previous.lat != next.lat || previous.lon != next.lon) path.add(next);
                }
            }
        }
        return path;
    }

    private static String routeSummary(JSONObject response, String cityId) throws Exception {
        String city = cityId.equals("tula") ? "Тула" : "Владимир";
        int requested = response.optInt("requestedMinutes", response.getInt("totalMinutes"));
        int unused = response.optInt("unusedMinutes", Math.max(0, requested - response.getInt("totalMinutes")));
        StringBuilder summary = new StringBuilder("Маршрут готов: " + city + ", " +
                response.getInt("totalMinutes") + " из " + requested + " мин. · версия " + response.getInt("routeVersion") +
                "\nПожелания: " + response.getString("query"));
        if (unused > 0) summary.append("\nСвободный резерв: ").append(unused).append(" мин.");
        JSONObject area = response.getJSONObject("searchArea");
        summary.append("\nОбласть поиска: ").append(area.getString("label"));
        if (response.optBoolean("approximateStart")) {
            summary.append("\nСтарт без геопозиции: ").append(area.getString("label"));
        }
        JSONArray points = response.getJSONArray("points");
        JSONArray legs = response.getJSONArray("legs");
        summary.append("\n\nТочки маршрута:");
        for (int i = 0; i < points.length(); i++) {
            JSONObject point = points.getJSONObject(i);
            summary.append("\n").append(i + 1).append(". ").append(point.getString("name"));
            summary.append(" — ").append(point.getInt("visitMinutes")).append(" мин.");
            if (point.optBoolean("isFood")) summary.append(" (еда)");
            String schedule = point.optString("scheduleStatus");
            if (schedule.equals("OPEN")) summary.append(" · открыто");
            if (schedule.equals("UNKNOWN")) summary.append(" · часы не указаны");
            if (i < legs.length()) {
                JSONObject leg = legs.getJSONObject(i);
                int walkingMinutes = (int) Math.ceil(leg.getInt("durationSeconds") / 60.0);
                summary.append("\n   Пешком: ").append(leg.getInt("distanceMeters"))
                        .append(" м, ≈").append(walkingMinutes).append(" мин.");
            }
        }
        JSONArray warnings = response.optJSONArray("warnings");
        if (warnings != null && warnings.length() > 0) {
            summary.append("\n\nВажно:");
            for (int i = 0; i < warnings.length(); i++) {
                summary.append("\n• ").append(warnings.getString(i));
            }
        }
        return summary.toString();
    }

    private static String humanError(String code, String message) {
        switch (code) {
            case "RATE_LIMITED": return message.isEmpty() ? "Лимит запросов 2ГИС. Подождите и повторите." : message;
            case "GEO_UNAVAILABLE": return message.isEmpty() ? "Данные 2ГИС недоступны. Попробуйте позже." : message;
            case "GEO_CONSTRAINT_NOT_FOUND": return "Не удалось найти указанную часть города. Сформулируйте район или ориентир точнее.";
            case "LLM_UNAVAILABLE": return "Разбор запроса недоступен. Проверьте ключ LLM и работу backend.";
            case "LLM_AUTH_ERROR": return "Сервер не принял ключ LLM. Проверьте настройки backend.";
            case "LLM_INVALID_RESPONSE": return "Не удалось разобрать пожелания. Попробуйте ещё раз.";
            case "QUERY_NEEDS_CLARIFICATION": return "Проверьте выбранный город и длительность прогулки.";
            case "ROUTE_NOT_FOUND": return message.isEmpty() ?
                    "Подходящих мест не найдено. Измените пожелания." : message;
            case "TIME_BUDGET_EXCEEDED": return message.isEmpty() ?
                    "Маршрут не помещается в выбранное время." : message;
            case "VERSION_CONFLICT": return "Маршрут уже изменился. Повторите правку с актуальной версии.";
            case "VALIDATION_ERROR": return "Проверьте город и текст запроса.";
            case "UNAUTHORIZED": return "Сессия истекла. Перезапустите приложение.";
            default: return message.isEmpty() ? "Не удалось получить маршрут: " + code : message;
        }
    }
}
