package ru.gulyay.app;

/** Pure timing and freshness rules for walk GPS submissions. */
final class PositionSubmissionPolicy {
    static final long LOCATION_UPDATE_INTERVAL_MILLIS = 12_000L;
    static final long WINDOW_MILLIS = 60_000L;
    static final long MIN_INTERVAL_MILLIS = 5_000L;
    static final long MAX_LOCATION_AGE_MILLIS = 30_000L;
    static final float MAX_ACCURACY_METERS = 50f;

    private PositionSubmissionPolicy() { }

    static boolean isFresh(long measuredElapsedMillis, long nowElapsedMillis,
                           long lastSubmittedMeasurementElapsedMillis) {
        return measuredElapsedMillis > 0
                && measuredElapsedMillis > lastSubmittedMeasurementElapsedMillis
                && measuredElapsedMillis <= nowElapsedMillis + 1_000L
                && nowElapsedMillis - measuredElapsedMillis <= MAX_LOCATION_AGE_MILLIS;
    }

    static long delayUntilSlot(long nowElapsedMillis, long previousSentAt,
                               long latestSentAt) {
        if (previousSentAt > nowElapsedMillis || latestSentAt > nowElapsedMillis) return 0L;
        long intervalDelay = latestSentAt <= 0 ? 0L
                : latestSentAt + MIN_INTERVAL_MILLIS - nowElapsedMillis;
        long windowDelay = previousSentAt <= 0 ? 0L
                : previousSentAt + WINDOW_MILLIS - nowElapsedMillis;
        return Math.max(0L, Math.max(intervalDelay, windowDelay));
    }
}
