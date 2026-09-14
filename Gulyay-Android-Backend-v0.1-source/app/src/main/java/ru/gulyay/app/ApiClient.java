package ru.gulyay.app;

import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.UUID;

final class ApiClient {
    private ApiClient() { }

    static String createRoute(String cityId, String query, String sessionId) throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL(
                BuildConfig.BACKEND_BASE_URL + "/v1/routes").openConnection();
        connection.setRequestMethod("POST");
        connection.setConnectTimeout(7000);
        connection.setReadTimeout(15000);
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
            connection.getOutputStream().write(bytes);
            int status = connection.getResponseCode();
            InputStream stream = status < 400 ? connection.getInputStream() : connection.getErrorStream();
            ByteArrayOutputStream buffer = new ByteArrayOutputStream();
            byte[] chunk = new byte[4096];
            int n;
            while ((n = stream.read(chunk)) != -1) buffer.write(chunk, 0, n);
            String body = buffer.toString("UTF-8");
            JSONObject response = new JSONObject(body);
            if (status >= 400) {
                JSONObject error = response.optJSONObject("error");
                if (error == null) return "Ошибка сервера (" + status + ")";
                return humanError(error.optString("code"), error.optString("message"));
            }
            return "Маршрут построен. Версия: " + response.optInt("routeVersion") +
                    ", точек: " + response.getJSONArray("points").length();
        } finally {
            connection.disconnect();
        }
    }

    private static String humanError(String code, String message) {
        switch (code) {
            case "GEO_UNAVAILABLE": return "Данные 2ГИС пока недоступны. Попробуйте позже.";
            case "QUERY_NEEDS_CLARIFICATION": return "Уточните город и длительность прогулки.";
            case "ROUTE_NOT_FOUND": return "Подходящих мест не найдено. Измените пожелания.";
            case "TIME_BUDGET_EXCEEDED": return "Маршрут не помещается в выбранное время.";
            case "VALIDATION_ERROR": return "Проверьте город и текст запроса.";
            case "UNAUTHORIZED": return "Сессия истекла. Перезапустите приложение.";
            default: return message.isEmpty() ? "Не удалось получить маршрут: " + code : message;
        }
    }
}
