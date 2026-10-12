package ru.gulyay.app;

/** Pure recovery decisions shared by MainActivity and its JVM regression tests. */
final class RouteLifecycleRecovery {
    enum HistoryRouteState { UNCONFIRMED, READY, TERMINAL, REMOVED }

    private RouteLifecycleRecovery() { }

    static HistoryRouteState fromRouteLookup(boolean routeLookupCompleted, boolean routeFound,
                                             String walkStatus) {
        if (!routeLookupCompleted) return HistoryRouteState.UNCONFIRMED;
        if (!routeFound) return HistoryRouteState.REMOVED;
        return isTerminal(walkStatus) ? HistoryRouteState.TERMINAL : HistoryRouteState.READY;
    }

    static boolean isCurrentHistoryResponse(int responseGeneration, int currentGeneration) {
        return responseGeneration == currentGeneration;
    }

    static boolean shouldReplaceHistoryCards(boolean historyLoaded, int responseGeneration,
                                             int currentGeneration) {
        return historyLoaded && isCurrentHistoryResponse(responseGeneration, currentGeneration);
    }

    static boolean isCurrentRouteStateRequest(String requestedRouteId, int requestedGeneration,
                                              String currentRouteId, int currentGeneration) {
        return requestedRouteId != null && requestedRouteId.equals(currentRouteId)
                && requestedGeneration == currentGeneration;
    }

    static boolean canDeleteHistoryRoute(String walkStatus) {
        return !"ACTIVE".equals(walkStatus) && !"PAUSED".equals(walkStatus);
    }

    static boolean canOpenUnconfirmedSnapshot(boolean walkStateVerified,
                                              boolean snapshotValid) {
        return !walkStateVerified && snapshotValid;
    }

    static String historyStatusLabel(String status) {
        if ("ACTIVE".equals(status)) return "Прогулка идёт";
        if ("PAUSED".equals(status)) return "Прогулка на паузе";
        if ("STOPPED".equals(status)) return "Прогулка остановлена";
        if ("COMPLETED".equals(status)) return "Маршрут пройден";
        return "Маршрут готов";
    }

    private static boolean isTerminal(String status) {
        return "STOPPED".equals(status) || "COMPLETED".equals(status);
    }
}
