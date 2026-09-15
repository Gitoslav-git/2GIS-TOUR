package ru.gulyay.app;

import org.json.JSONObject;
import org.json.JSONArray;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.UUID;

final class ApiClient {
    private ApiClient() { }

    static String createRoute(String cityId, String query, String sessionId) throws Exception {
        if (BuildConfig.BACKEND_BASE_URL.equals("https://example.invalid")) {
            return "Для построения маршрута нужен адрес запущенного backend. Эта сборка пока не подключена к серверу.";
        }
        HttpURLConnection connection = (HttpURLConnection) new URL(
                BuildConfig.BACKEND_BASE_URL + "/v1/routes").openConnection();
        connection.setRequestMethod("POST");
        connection.setConnectTimeout(7000);
        connection.setReadTimeout(60000);
        connection.setDoOutput(true);
        connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
        connection.setRequestProperty("X-Device-Session", sessionId);
        connection.setRequestProperty("X-Request-Id", UUID.randomUUID().toString());
        JSONObject payload = new JSONObject();
        payload.put("cityId", cityId);
        payload.put("query", query);
        payload.put("deviceSessionId", sessionId);
        payload.put("filters", new JSONObject());
        byte[] bytes = payload.toString().getBytes(StandardCharsets.UTF_8);
        try {
            try (java.io.OutputStream output = connection.getOutputStream()) {
                output.write(bytes);
            }
            int status = connection.getResponseCode();
            InputStream stream = status < 400 ? connection.getInputStream() : connection.getErrorStream();
            if (stream == null) return "Backend вернул пустой ответ (" + status + ")";
            ByteArrayOutputStream buffer = new ByteArrayOutputStream();
            byte[] chunk = new byte[4096];
            try (InputStream input = stream) {
                int n;
                while ((n = input.read(chunk)) != -1) buffer.write(chunk, 0, n);
            }
            String body = buffer.toString("UTF-8");
            if (body.trim().isEmpty()) return "Backend вернул пустой ответ (" + status + ")";
            JSONObject response = new JSONObject(body);
            if (status >= 400) {
                JSONObject error = response.optJSONObject("error");
                if (error == null) return "Ошибка сервера (" + status + ")";
                return humanError(error.optString("code"), error.optString("message"));
            }
            String city = cityId.equals("tula") ? "Тула" : "Владимир";
            StringBuilder summary = new StringBuilder("Маршрут готов: " + city + ", " +
                    response.getInt("totalMinutes") + " мин.\nПожелания: " + query);
            if (response.optBoolean("approximateStart")) {
                summary.append("\nСтарт: центр выбранного города");
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
        } finally {
            connection.disconnect();
        }
    }

    private static String humanError(String code, String message) {
        switch (code) {
            case "GEO_UNAVAILABLE": return message.isEmpty() ? "Данные 2ГИС недоступны. Попробуйте позже." : message;
            case "LLM_UNAVAILABLE": return "Разбор запроса недоступен. Проверьте ключ LLM и работу backend.";
            case "LLM_AUTH_ERROR": return "Сервер не принял ключ LLM. Проверьте настройки backend.";
            case "LLM_INVALID_RESPONSE": return "Не удалось разобрать пожелания. Попробуйте ещё раз.";
            case "QUERY_NEEDS_CLARIFICATION": return "Проверьте выбранный город и длительность прогулки.";
            case "ROUTE_NOT_FOUND": return "Подходящих мест не найдено. Измените пожелания.";
            case "TIME_BUDGET_EXCEEDED": return "Маршрут не помещается в выбранное время.";
            case "VALIDATION_ERROR": return "Проверьте город и текст запроса.";
            case "UNAUTHORIZED": return "Сессия истекла. Перезапустите приложение.";
            default: return message.isEmpty() ? "Не удалось получить маршрут: " + code : message;
        }
    }
}
