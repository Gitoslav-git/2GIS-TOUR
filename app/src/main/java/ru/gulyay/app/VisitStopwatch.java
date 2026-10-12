package ru.gulyay.app;

import java.util.Locale;

/** Pure visit stopwatch math used by the UI and JVM regression tests. */
final class VisitStopwatch {
    private VisitStopwatch() { }

    static int elapsedSeconds(int backendSeconds, long syncedAtElapsedMillis,
                              long nowElapsedMillis, boolean running) {
        if (!running) return Math.max(0, backendSeconds);
        long localSeconds = Math.max(0L, nowElapsedMillis - syncedAtElapsedMillis) / 1_000L;
        return (int) Math.min(Integer.MAX_VALUE, Math.max(0L, backendSeconds) + localSeconds);
    }

    static String format(int seconds) {
        int safe = Math.max(0, seconds);
        int hours = safe / 3600;
        int minutes = (safe % 3600) / 60;
        int remainder = safe % 60;
        if (hours > 0) return String.format(Locale.US, "%d:%02d:%02d",
                hours, minutes, remainder);
        return String.format(Locale.US, "%02d:%02d", minutes, remainder);
    }
}
