package ru.gulyay.app;

/** Pure guards for callbacks from a MapView that may have already been removed. */
final class MapLifecycleGuard {
    private MapLifecycleGuard() { }

    static boolean shouldApplyMapCallback(Object requestedMapView, Object currentMapView,
                                          boolean initializationInProgress, boolean activityAlive) {
        return activityAlive && initializationInProgress && requestedMapView == currentMapView;
    }
}
