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

    static String interpret(String cityId, String query, String sessionId) throws Exception {
        if (BuildConfig.BACKEND_BASE_URL.equals("https://example.invalid")) {
            return "Для разбора пожеланий нужен адрес запущенного backend. Эта сборка пока не подключена к серверу.";
        }
        HttpURLConnection connection = (HttpURLConnection) new URL(
                BuildConfig.BACKEND_BASE_URL + "/v1/routes/interpret").openConnection();
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
            JSONObject response = new JSONObject(body);
            if (status >= 400) {
                JSONObject error = response.optJSONObject("error");
                if (error == null) return "Ошибка сервера (" + status + ")";
                return humanError(error.optString("code"), error.optString("message"));
            }
            String city = cityId.equals("tula") ? "Тула" : "Владимир";
            StringBuilder summary = new StringBuilder("Пожелания разобраны: " + city + ", " +
                    response.getInt("durationMinutes") + " мин.");
            String source = response.optString("durationSource");
            if (source.equals("default")) summary.append(" (время по умолчанию)");
            if (source.equals("filter")) summary.append(" (время из фильтра)");
            JSONArray interests = response.optJSONArray("interests");
            if (interests != null && interests.length() > 0) {
                summary.append("\nИнтересы: ");
                for (int i = 0; i < interests.length(); i++) {
                    if (i > 0) summary.append(", ");
                    summary.append(interests.getString(i));
                }
            }
            summary.append("\nЕда: ").append(response.optBoolean("includeFood") ? "да" : "нет");
            if (response.optBoolean("withChildren")) summary.append("\nПрогулка с детьми");
            if (response.optBoolean("unusualPlaces")) summary.append("\nИнтересуют необычные места");
            JSONArray warnings = response.optJSONArray("warnings");
            if (warnings != null) for (int i = 0; i < warnings.length(); i++) {
                summary.append("\n").append(warnings.getString(i));
            }
            summary.append("\nМаршрут ещё не построен: поиск реальных мест 2ГИС — следующий этап.");
            return summary.toString();
        } finally {
            connection.disconnect();
        }
    }

    private static String humanError(String code, String message) {
        switch (code) {
            case "GEO_UNAVAILABLE": return "Данные 2ГИС пока недоступны. Попробуйте позже.";
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
