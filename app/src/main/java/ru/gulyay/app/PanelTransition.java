package ru.gulyay.app;

/** Pure rules for automatic route-panel movement. */
final class PanelTransition {
    private PanelTransition() { }

    static boolean isNewArrival(String previousRouteKey, String currentRouteKey,
                                String previousPhase, int previousPointOrder,
                                String currentPhase, int currentPointOrder) {
        return currentRouteKey != null && currentRouteKey.equals(previousRouteKey)
                && "MOVING".equals(previousPhase)
                && "VISITING".equals(currentPhase)
                && currentPointOrder > 0
                && currentPointOrder == previousPointOrder;
    }
}
