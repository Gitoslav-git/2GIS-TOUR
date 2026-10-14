package ru.gulyay.app;

/** Immutable GPS measurement used only when starting a new route. */
final class RouteStartLocation {
    static final long MAX_AGE_MILLIS = 60_000L;
    static final double MAX_ACCURACY_METERS = 100.0;

    final double lat;
    final double lon;
    final double accuracyMeters;
    final long measuredAtMillis;

    RouteStartLocation(double lat, double lon, double accuracyMeters, long measuredAtMillis) {
        this.lat = lat;
        this.lon = lon;
        this.accuracyMeters = accuracyMeters;
        this.measuredAtMillis = measuredAtMillis;
    }

    boolean isFreshAndAccurate(long nowMillis) {
        long age = nowMillis - measuredAtMillis;
        return Double.isFinite(lat) && lat >= -90.0 && lat <= 90.0
                && Double.isFinite(lon) && lon >= -180.0 && lon <= 180.0
                && Double.isFinite(accuracyMeters) && accuracyMeters >= 0.0
                && accuracyMeters <= MAX_ACCURACY_METERS
                && measuredAtMillis > 0L && age >= 0L && age <= MAX_AGE_MILLIS;
    }
}
