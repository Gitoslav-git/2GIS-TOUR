package ru.gulyay.app;

import org.json.JSONArray;
import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.UUID;

final class ApiClient {
    private ApiClient() { }

    static final class Result {
        final boolean success;
        final String message;
        final String routeId;
        final int routeVersion;
        final int retryAfterSeconds;
        final String errorCode;

        Result(boolean success, String message, String routeId, int routeVersion) {
            this(success, message, routeId, routeVersion, 0, null);
        }

        Result(boolean success, String message, String routeId, int routeVersion,
               int retryAfterSeconds, String errorCode) {
            this.success = success;
            this.message = message;
            this.routeId = routeId;
            this.routeVersion = routeVersion;
            this.retryAfterSeconds = retryAfterSeconds;
            this.errorCode = errorCode;
        }
    }

    static Result createRoute(String cityId, String query, String sessionId) throws Exception {
        JSONObject payload = new JSONObject();
        payload.put("cityId", cityId);
        payload.put("query", query);
        payload.put("deviceSessionId", sessionId);
        payload.put("filters", new JSONObject());
        return send("/v1/routes", payload, sessionId, cityId);
    }

    static Result reviseRoute(String routeId, int baseVersion, String cityId,
                              String query, String sessionId) throws Exception {
        JSONObject payload = new JSONObject();
        payload.put("baseVersion", baseVersion);
        payload.put("mode", "CHANGE_QUERY");
        payload.put("query", query);
        Result revised = send("/v1/routes/" + routeId + "/revisions", payload, sessionId, cityId);
        if (!revised.success && "NOT_FOUND".equals(revised.errorCode)) {
            Result recreated = createRoute(cityId, query, sessionId);
            if (recreated.success) {
                return new Result(true, "Старый маршрут отсутствовал на сервере — построен новый.\n\n" +
                        recreated.message, recreated.routeId, recreated.routeVersion);
            }
            return recreated;
        }
        return revised;
    }

    private static Result send(String path, JSONObject payload, String sessionId,
                               String cityId) throws Exception {
        if (BuildConfig.BACKEND_BASE_URL.equals("https://example.invalid")) {
            return new Result(false, "Для построения маршрута нужен адрес запущенного backend. Эта сборка пока не подключена к серверу.", null, 0);
        }
        HttpURLConnection connection = (HttpURLConnection) new URL(
                BuildConfig.BACKEND_BASE_URL + path).openConnection();
        connection.setRequestMethod("POST");
        connection.setConnectTimeout(7000);
        connection.setReadTimeout(60000);
        connection.setDoOutput(true);
        connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
        connection.setRequestProperty("X-Device-Session", sessionId);
        connection.setRequestProperty("X-Request-Id", UUID.randomUUID().toString());
        byte[] bytes = payload.toString().getBytes(StandardCharsets.UTF_8);
        try {
            try (java.io.OutputStream output = connection.getOutputStream()) {
                output.write(bytes);
            }
            int status = connection.getResponseCode();
            InputStream stream = status < 400 ? connection.getInputStream() : connection.getErrorStream();
            if (stream == null) return new Result(false, "Backend вернул пустой ответ (" + status + ")", null, 0);
            ByteArrayOutputStream buffer = new ByteArrayOutputStream();
            byte[] chunk = new byte[4096];
            try (InputStream input = stream) {
                int n;
                while ((n = input.read(chunk)) != -1) buffer.write(chunk, 0, n);
            }
            String body = buffer.toString("UTF-8");
            if (body.trim().isEmpty()) return new Result(false, "Backend вернул пустой ответ (" + status + ")", null, 0);
            JSONObject response = new JSONObject(body);
            if (status >= 400) {
                JSONObject error = response.optJSONObject("error");
                if (error == null) return new Result(false, "Ошибка сервера (" + status + ")", null, 0);
                JSONObject details = error.optJSONObject("details");
                int retryAfter = details == null ? 0 : details.optInt("retryAfterSeconds", 0);
                String code = error.optString("code");
                return new Result(false, humanError(code, error.optString("message")),
                        null, 0, retryAfter, code);
            }
            return new Result(true, routeSummary(response, cityId), response.getString("routeId"),
                    response.getInt("routeVersion"));
        } finally {
            connection.disconnect();
        }
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
            case "ROUTE_NOT_FOUND": return "Подходящих мест не найдено. Измените пожелания.";
            case "TIME_BUDGET_EXCEEDED": return "Маршрут не помещается в выбранное время.";
            case "VERSION_CONFLICT": return "Маршрут уже изменился. Повторите правку с актуальной версии.";
            case "VALIDATION_ERROR": return "Проверьте город и текст запроса.";
            case "UNAUTHORIZED": return "Сессия истекла. Перезапустите приложение.";
            default: return message.isEmpty() ? "Не удалось получить маршрут: " + code : message;
        }
    }
}
