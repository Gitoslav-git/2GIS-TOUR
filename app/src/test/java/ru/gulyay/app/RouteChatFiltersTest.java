package ru.gulyay.app;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertTrue;

import org.json.JSONObject;
import org.junit.Test;

public class RouteChatFiltersTest {
    private static final String ALL_FILTERS = "{"
            + "\"durationMinutes\":120,"
            + "\"withChildren\":true,"
            + "\"includeFood\":true,"
            + "\"unusualPlaces\":true}";

    @Test public void preservesAllQuickFiltersWithGpsAndAcrossRetries() throws Exception {
        RouteChatFilters filters = RouteChatFilters.fromExtra(ALL_FILTERS);
        assertNotNull(filters);

        JSONObject first = ApiClient.createRoutePayload("moscow", "walk", "session",
                55.75, 37.61, 12.0, filters.copyJson());
        JSONObject retry = ApiClient.createRoutePayload("moscow", "walk", "session",
                55.75, 37.61, 12.0, filters.copyJson());

        assertAllFilters(first.getJSONObject("filters"));
        assertAllFilters(retry.getJSONObject("filters"));
        assertEquals(55.75, first.getJSONObject("startLocation").getDouble("lat"), 0.0);
    }

    @Test public void preservesAllQuickFiltersWhenStartingFromCityCenter() throws Exception {
        RouteChatFilters filters = RouteChatFilters.fromExtra(ALL_FILTERS);
        JSONObject payload = ApiClient.createRoutePayload("moscow", "walk", "session",
                null, null, null, filters.copyJson());

        assertAllFilters(payload.getJSONObject("filters"));
        assertFalse(payload.has("startLocation"));
    }

    @Test public void existingRouteKeepsBackendFiltersUntilUserChangesQuickFilters() {
        assertFalse(RouteChatFilters.shouldSend(true, false));
        assertTrue(RouteChatFilters.shouldSend(true, true));
        assertTrue(RouteChatFilters.shouldSend(false, false));
    }

    private static void assertAllFilters(JSONObject filters) throws Exception {
        assertEquals(120, filters.getInt("durationMinutes"));
        assertEquals(true, filters.getBoolean("withChildren"));
        assertEquals(true, filters.getBoolean("includeFood"));
        assertEquals(true, filters.getBoolean("unusualPlaces"));
    }
}
