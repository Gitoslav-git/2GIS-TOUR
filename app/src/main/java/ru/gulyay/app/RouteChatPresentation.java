package ru.gulyay.app;

/** Pure chat presentation rules kept outside Activity for JVM regression tests. */
final class RouteChatPresentation {
    private RouteChatPresentation() { }

    static String routeMessage(ApiClient.Result result) {
        if (result.message != null && !result.message.trim().isEmpty()) {
            return result.message.trim();
        }
        String duration = result.totalMinutes > 0
                ? result.totalMinutes + " мин."
                : "несколько минут";
        return "Маршрут готов: " + duration;
    }
}
