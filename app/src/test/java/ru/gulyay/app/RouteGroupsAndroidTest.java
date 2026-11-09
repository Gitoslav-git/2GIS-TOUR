package ru.gulyay.app;

import static org.junit.Assert.*;

import java.util.Arrays;
import java.util.Collections;
import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;

public final class RouteGroupsAndroidTest {
    @Test public void createPayloadOptsInAtTopLevelOnly() throws Exception {
        JSONObject filters = new JSONObject().put("pace", "CALM");
        JSONObject payload = ApiClient.createRoutePayload("moscow", "walk", "s",
                null, null, null, filters, true);
        assertTrue(payload.getBoolean("routeGroupsEnabled"));
        assertFalse(payload.getJSONObject("filters").has("routeGroupsEnabled"));
        assertFalse(ApiClient.createRoutePayload("moscow", "walk", "s",
                null, null, null, filters, false).has("routeGroupsEnabled"));
    }

    @Test public void parsesB2GroupsAndLonLatGeometry() throws Exception {
        ApiClient.Result route = ApiClient.routeFromJson(b2Route(), "moscow");
        assertTrue(route.routeGroupsEnabled);
        assertEquals(1, route.routeGroups.size());
        ApiClient.RouteGroup group = route.routeGroups.get(0);
        assertEquals(1, group.pointOrder);
        assertEquals("msk005", group.catalogId);
        assertEquals(2, group.waypoints.size());
        assertEquals("CONTAINS", group.waypoints.get(0).relation);
        assertEquals(1, group.waypointLegs.size());
        ApiClient.GeoCoordinate first = group.waypointLegs.get(0).path.get(0);
        assertEquals(55.751, first.lat, 0.000001);
        assertEquals(37.617, first.lon, 0.000001);
    }

    @Test public void legacyJsonRemainsUngrouped() throws Exception {
        JSONObject legacy = baseRoute();
        ApiClient.Result route = ApiClient.routeFromJson(legacy, "moscow");
        assertFalse(route.routeGroupsEnabled);
        assertTrue(route.routeGroups.isEmpty());
        assertEquals(1, route.points.size());
    }

    @Test public void snapshotRoundTripKeepsGroupAndRequiredGeometry() throws Exception {
        ApiClient.Result source = ApiClient.routeFromJson(b2Route(), "moscow");
        ApiClient.Result restored = ApiClient.routeFromSnapshot(ApiClient.routeSnapshot(source));
        assertNotNull(restored);
        assertTrue(restored.routeGroupsEnabled);
        assertEquals(1, restored.routeGroups.size());
        assertEquals(1, restored.routeGroups.get(0).waypointLegs.size());
        assertEquals(55.751, restored.routeGroups.get(0).waypointLegs.get(0).path.get(0).lat,
                0.000001);
        assertEquals(1, restored.legGeometries.size());
    }

    @Test public void incompleteGroupedSnapshotForcesReload() throws Exception {
        JSONObject snapshot = new JSONObject()
                .put("routeId", "r").put("routeVersion", 1).put("routeGroupsEnabled", true)
                .put("points", new JSONArray()).put("path", new JSONArray());
        assertNull(ApiClient.routeFromSnapshot(snapshot.toString()));
    }

    @Test public void presentationDeduplicatesPinsAndNeverInventsSegments() {
        ApiClient.Result route = sampleResult();
        assertEquals(1, RouteGroupSupport.uniqueChildMarkers(route).size());
        assertEquals("child", RouteGroupSupport.uniqueChildMarkers(route).get(0).placeId);
        assertEquals(1, RouteGroupSupport.realGeometrySegments(route).size());
        assertEquals(1, RouteGroupSupport.drawableSegments(route).size());
    }

    @Test public void backendLegsStaySeparateFromInternalLegs() throws Exception {
        ApiClient.Result route = ApiClient.routeFromJson(b2Route(), "moscow");
        assertEquals(2, RouteGroupSupport.drawableSegments(route).size());
        assertNotSame(RouteGroupSupport.drawableSegments(route).get(0),
                RouteGroupSupport.drawableSegments(route).get(1));
    }

    @Test public void navigationProgressChangesChildWithoutChangingLogicalOrder() {
        ApiClient.Result route = sampleResult();
        ApiClient.WalkResult walk = new ApiClient.WalkResult(true, "", "w", "ACTIVE",
                1, 10, false, 0, null, 0, "VISITING", 30, false);
        ApiClient.RouteGroup group = route.routeGroups.get(0);
        RouteGroupSupport.NavigationTarget target = RouteGroupSupport.navigationTarget(group,
                55.751, 37.617, 0, 0);
        assertNotNull(target);
        assertEquals("Child", target.waypoint.name);
        assertEquals(1, walk.currentPointOrder);
        assertTrue(RouteGroupSupport.hasActiveGroup(route, walk));
    }

    @Test public void groupedBoundaryUsesServerDistanceNotParentCenter() {
        ApiClient.Result route = sampleResult();
        ApiClient.WalkResult grouped = new ApiClient.WalkResult(true, "", "w", "ACTIVE",
                1, 10, false, 8, null, 0, "VISITING", 30, false);
        assertEquals(8, RouteGroupSupport.boundaryDistance(route, grouped, 2500));
        grouped = new ApiClient.WalkResult(true, "", "w", "ACTIVE",
                2, 10, false, 8, null, 0, "MOVING", 0, false);
        assertEquals(2500, RouteGroupSupport.boundaryDistance(route, grouped, 2500));
    }

    @Test public void groupedEditErrorIsFriendly() {
        String text = ApiClient.humanError("GROUPED_ROUTE_EDIT_UNSUPPORTED", "");
        assertTrue(text.contains("пока недоступны"));
        assertTrue(text.contains("помощником"));
    }

    @Test public void validationErrorKeepsBackendReasonInsteadOfInventingCityProblem() {
        String text = ApiClient.humanError("VALIDATION_ERROR", "Проверьте заполненные поля");
        assertFalse(text.contains("Проверьте город"));
        if (BuildConfig.ROUTE_GROUPS_ENABLED) assertTrue(text.contains("routeGroupsEnabled"));
        else assertEquals("Проверьте заполненные поля", text);
    }

    @Test public void validationDetailsExplainOldBackendRouteGroupsMismatch() throws Exception {
        JSONObject details = new JSONObject().put("errors", new JSONArray().put(
                new JSONObject().put("field", "routeGroupsEnabled")
                        .put("type", "extra_forbidden")));
        String text = ApiClient.humanError("VALIDATION_ERROR", "", details);
        assertTrue(text.contains("routeGroupsEnabled"));
        assertTrue(text.contains("Обновите backend"));
    }

    @Test public void routeCreateLogSummaryContainsUsefulFieldsButNoSecrets() throws Exception {
        JSONObject payload = ApiClient.createRoutePayload("moscow", "Хочу погулять 5 часов",
                "secret-session", 55.75, 37.61, 5.0,
                new JSONObject().put("includeFood", true).put("unknownSecret", "hidden"), true);
        String summary = ApiClient.createRouteLogSummary(payload);
        assertTrue(summary.contains("cityId=moscow"));
        assertTrue(summary.contains("Хочу погулять 5 часов"));
        assertTrue(summary.contains("includeFood"));
        assertTrue(summary.contains("routeGroupsEnabled=true"));
        assertTrue(summary.contains("startLocationPresent=true"));
        assertFalse(summary.contains("secret-session"));
        assertFalse(summary.contains("deviceSessionId"));
        assertFalse(summary.contains("55.75"));
        assertFalse(summary.contains("unknownSecret"));
    }

    private static JSONObject baseRoute() throws Exception {
        return new JSONObject().put("routeId", "r").put("routeVersion", 1)
                .put("totalMinutes", 20).put("query", "walk")
                .put("searchArea", new JSONObject().put("label", "center"))
                .put("points", new JSONArray().put(new JSONObject()
                        .put("placeId", "parent").put("catalogId", "msk005")
                        .put("name", "Parent").put("lat", 55.75).put("lon", 37.61)
                        .put("visitMinutes", 20)))
                .put("legs", new JSONArray().put(new JSONObject().put("toOrder", 1)
                        .put("distanceMeters", 100).put("durationSeconds", 80)
                        .put("geometry", new JSONArray()
                                .put(new JSONArray().put(37.60).put(55.74))
                                .put(new JSONArray().put(37.61).put(55.75)))));
    }

    private static JSONObject b2Route() throws Exception {
        return baseRoute().put("routeGroupsEnabled", true)
                .put("routeGroups", new JSONArray().put(new JSONObject()
                        .put("pointOrder", 1).put("catalogId", "msk005")
                        .put("waypoints", new JSONArray()
                                .put(new JSONObject().put("order", 1).put("catalogId", "msk050")
                                        .put("placeId", "child").put("name", "Child")
                                        .put("lat", 55.751).put("lon", 37.617)
                                        .put("relation", "CONTAINS"))
                                .put(new JSONObject().put("order", 2).put("catalogId", "msk051")
                                        .put("placeId", "child2").put("name", "Child 2")
                                        .put("lat", 55.752).put("lon", 37.618)
                                        .put("relation", "CLUSTER_MEMBER")))
                        .put("waypointLegs", new JSONArray().put(new JSONObject()
                                .put("fromWaypointOrder", 0).put("toWaypointOrder", 1)
                                .put("distanceMeters", 90).put("durationSeconds", 70)
                                .put("geometry", new JSONArray()
                                        .put(new JSONArray().put(37.617).put(55.751))
                                        .put(new JSONArray().put(37.6175).put(55.7515)))))));
    }

    private static ApiClient.Result sampleResult() {
        ApiClient.PlaceOption parent = new ApiClient.PlaceOption("parent", "msk005",
                "Parent", false, 55.75, 37.61);
        ApiClient.Result route = new ApiClient.Result(true, "", "r", 1, 0, null,
                Collections.singletonList(parent), Collections.emptyList());
        ApiClient.RouteWaypoint duplicate = new ApiClient.RouteWaypoint(1, "msk005", "parent",
                "Parent duplicate", 55.75, 37.61, "CONTAINS");
        ApiClient.RouteWaypoint child = new ApiClient.RouteWaypoint(2, "msk050", "child",
                "Child", 55.751, 37.617, "CONTAINS");
        ApiClient.RouteWaypointLeg leg = new ApiClient.RouteWaypointLeg(0, 2, 80, 60,
                Arrays.asList(new ApiClient.GeoCoordinate(55.75, 37.61),
                        new ApiClient.GeoCoordinate(55.751, 37.617)));
        route.routeGroupsEnabled = true;
        route.routeGroups = Collections.singletonList(new ApiClient.RouteGroup(1, "msk005",
                Arrays.asList(duplicate, child), Collections.singletonList(leg)));
        return route;
    }
}
