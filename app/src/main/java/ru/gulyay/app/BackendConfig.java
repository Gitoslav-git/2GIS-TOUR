package ru.gulyay.app;

import android.os.Build;
import android.util.Log;

import java.net.MalformedURLException;
import java.net.URL;
import java.util.Locale;

/** Single source of truth for every backend request made by the Android client. */
final class BackendConfig {
    static final String LOG_TAG = "GulyayNetwork";
    private static final String UNCONFIGURED_URL = "https://example.invalid";
    private static final boolean EMULATOR = detectEmulator();
    private static final String BASE_URL = normalizeAndValidate(selectBaseUrl());

    private BackendConfig() { }

    static String baseUrl() {
        return BASE_URL;
    }

    static boolean isConfigured() {
        return !UNCONFIGURED_URL.equals(BASE_URL);
    }

    static URL endpoint(String path) {
        if (path == null || !path.startsWith("/")) {
            throw new IllegalArgumentException("Backend endpoint must start with /");
        }
        try {
            return new URL(BASE_URL + path);
        } catch (MalformedURLException error) {
            throw new IllegalStateException("Invalid backend endpoint: " + path, error);
        }
    }

    static void logSelection() {
        Log.i(LOG_TAG, "Backend selected: mode=" + mode() + " url=" + BASE_URL);
    }

    static long logRequest(String method, String path) {
        Log.i(LOG_TAG, "HTTP start: method=" + method + " endpoint=" + path
                + " url=" + BASE_URL);
        return System.currentTimeMillis();
    }

    static void logResponse(String method, String path, int status, long startedAt) {
        Log.i(LOG_TAG, "HTTP response: method=" + method + " endpoint=" + path
                + " status=" + status + " elapsedMs="
                + Math.max(0L, System.currentTimeMillis() - startedAt));
    }

    static void logFailure(String method, String path, long startedAt, Throwable error) {
        Throwable root = rootCause(error);
        Log.e(LOG_TAG, "HTTP failure: method=" + method + " endpoint=" + path
                + " url=" + BASE_URL + " type=" + root.getClass().getSimpleName()
                + " elapsedMs=" + Math.max(0L, System.currentTimeMillis() - startedAt), error);
    }

    static String failureSummary(Throwable error) {
        Throwable root = rootCause(error);
        String message = root.getMessage();
        return root.getClass().getSimpleName()
                + (message == null || message.trim().isEmpty() ? "" : ": " + message.trim());
    }

    private static String selectBaseUrl() {
        if (!BuildConfig.DEBUG) return BuildConfig.BACKEND_BASE_URL;
        return EMULATOR
                ? BuildConfig.EMULATOR_BACKEND_BASE_URL
                : BuildConfig.DEVICE_BACKEND_BASE_URL;
    }

    private static String normalizeAndValidate(String raw) {
        String value = raw == null ? "" : raw.trim();
        while (value.endsWith("/") && value.length() > "https://x".length()) {
            value = value.substring(0, value.length() - 1);
        }
        try {
            URL parsed = new URL(value);
            String protocol = parsed.getProtocol();
            if (!("http".equals(protocol) || "https".equals(protocol))
                    || parsed.getHost() == null || parsed.getHost().trim().isEmpty()) {
                throw new MalformedURLException("HTTP(S) URL with host required");
            }
            if (!BuildConfig.DEBUG && !"https".equals(protocol)) {
                throw new MalformedURLException("Release backend must use HTTPS");
            }
            return value;
        } catch (MalformedURLException error) {
            throw new IllegalStateException("Invalid backend base URL", error);
        }
    }

    private static String mode() {
        if (!BuildConfig.DEBUG) return "release";
        return EMULATOR ? "emulator" : "physical-device";
    }

    private static boolean detectEmulator() {
        String fingerprint = lower(Build.FINGERPRINT);
        String model = lower(Build.MODEL);
        String manufacturer = lower(Build.MANUFACTURER);
        String brand = lower(Build.BRAND);
        String device = lower(Build.DEVICE);
        String product = lower(Build.PRODUCT);
        return fingerprint.startsWith("generic")
                || fingerprint.contains("emulator")
                || fingerprint.contains("vbox")
                || model.contains("google_sdk")
                || model.contains("emulator")
                || model.contains("android sdk built for")
                || manufacturer.contains("genymotion")
                || (brand.startsWith("generic") && device.startsWith("generic"))
                || product.contains("sdk_gphone")
                || product.contains("emulator")
                || product.contains("simulator");
    }

    private static String lower(String value) {
        return value == null ? "" : value.toLowerCase(Locale.US);
    }

    private static Throwable rootCause(Throwable error) {
        Throwable current = error == null ? new IllegalStateException("Unknown network error") : error;
        for (int depth = 0; depth < 8 && current.getCause() != null; depth++) {
            current = current.getCause();
        }
        return current;
    }
}
