package ru.gulyay.app;

import org.json.JSONObject;

/** Immutable copy of the quick filters carried through route-chat retries. */
final class RouteChatFilters {
    private final String serialized;

    private RouteChatFilters(String serialized) {
        this.serialized = serialized;
    }

    static RouteChatFilters fromExtra(String serialized) {
        if (serialized == null) return null;
        try {
            return new RouteChatFilters(new JSONObject(serialized).toString());
        } catch (Exception ignored) {
            return null;
        }
    }

    static boolean shouldSend(boolean editingCurrentRoute, boolean filtersChanged) {
        return !editingCurrentRoute || filtersChanged;
    }

    JSONObject copyJson() {
        try {
            return new JSONObject(serialized);
        } catch (Exception impossibleAfterValidation) {
            return new JSONObject();
        }
    }
}
