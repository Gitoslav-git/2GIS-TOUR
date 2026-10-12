package ru.gulyay.app;

/** Safety checks for the short-lived, read-only guest route snapshot. */
final class RouteSnapshotPolicy {
    static final long OFFLINE_VIEW_WINDOW_MILLIS = 24L * 60L * 60L * 1000L;

    private RouteSnapshotPolicy() { }

    static boolean isValidForOfflineView(String snapshotRouteId, int snapshotVersion,
                                         long savedAtElapsedMillis, long expiresAtElapsedMillis,
                                         String expectedRouteId, int expectedVersion,
                                         long nowElapsedMillis) {
        return snapshotRouteId != null && snapshotRouteId.equals(expectedRouteId)
                && snapshotVersion == expectedVersion
                && savedAtElapsedMillis > 0L
                && expiresAtElapsedMillis >= savedAtElapsedMillis
                // elapsedRealtime resets after a device reboot. Do not turn a
                // legacy snapshot into an indefinitely valid offline archive.
                && nowElapsedMillis >= savedAtElapsedMillis
                && nowElapsedMillis <= expiresAtElapsedMillis;
    }
}
