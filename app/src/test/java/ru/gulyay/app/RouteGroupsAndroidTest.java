package ru.gulyay.app;

import static org.junit.Assert.*;

import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
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

    @Test public void nizhnyNovgorodSelectionUsesBackendCityId() throws Exception {
        JSONObject payload = ApiClient.createRoutePayload(
                "nizhny_novgorod", "Прогулка на 2 часа", "session",
                null, null, null, new JSONObject(), true);
        assertEquals("nizhny_novgorod", payload.getString("cityId"));
    }

    @Test public void parsesFreeRoamChildrenIncludingListOnlyEntries() throws Exception {
        ApiClient.Result route = ApiClient.routeFromJson(freeRoamRoute(), "moscow");
        assertTrue(route.routeGroupsEnabled);
        ApiClient.RouteGroup group = route.routeGroups.get(0);
        assertEquals(1, group.pointOrder);
        assertEquals("msk005", group.catalogId);
        assertEquals(3, group.children.size());
        assertEquals("CONTAINS", group.children.get(0).relation);
        assertEquals("CLUSTER_MEMBER", group.children.get(1).relation);
        assertFalse(group.children.get(2).hasCoordinates());
        assertTrue(group.waypoints.isEmpty());
        assertTrue(group.waypointLegs.isEmpty());
        assertTrue(group.hasVisitZone);
    }

    @Test public void legacyB2GroupsRemainReadableAsChildren() throws Exception {
        JSONObject legacy = baseRoute().put("routeGroupsEnabled", true)
                .put("routeGroups", new JSONArray().put(new JSONObject()
                        .put("pointOrder", 1).put("catalogId", "msk005")
                        .put("children", new JSONArray())
                        .put("visitZone", new JSONObject().put("type", "Polygon")
                                .put("coordinates", new JSONArray()))
                        .put("waypoints", new JSONArray().put(new JSONObject()
                                .put("order", 1).put("catalogId", "msk050")
                                .put("placeId", "child").put("name", "Child")
                                .put("lat", 55.751).put("lon", 37.617)
                                .put("relation", "CONTAINS")))
                        .put("waypointLegs", new JSONArray().put(new JSONObject()
                                .put("fromWaypointOrder", 0).put("toWaypointOrder", 1)
                                .put("distanceMeters", 90).put("durationSeconds", 70)
                                .put("geometry", new JSONArray()
                                        .put(new JSONArray().put(37.617).put(55.751))
                                        .put(new JSONArray().put(37.618).put(55.752)))))));
        ApiClient.RouteGroup group = ApiClient.routeFromJson(legacy, "moscow")
                .routeGroups.get(0);
        assertEquals(1, group.children.size());
        assertEquals("Child", group.children.get(0).name);
        assertEquals(1, group.waypointLegs.size());
    }

    @Test public void routeWithoutGroupsRemainsUngrouped() throws Exception {
        ApiClient.Result route = ApiClient.routeFromJson(baseRoute(), "moscow");
        assertFalse(route.routeGroupsEnabled);
        assertTrue(route.routeGroups.isEmpty());
    }

    @Test public void degradedDurationWarningReachesRouteChatPresentation() throws Exception {
        JSONObject degraded = baseRoute()
                .put("totalMinutes", 134)
                .put("requestedMinutes", 360)
                .put("unusedMinutes", 226)
                .put("durationSource", "text")
                .put("planningStatus", "DEGRADED")
                .put("durationUtilization", 134.0 / 360.0)
                .put("warnings", new JSONArray().put(
                        "Вы просили 6 часов, удалось подобрать маршрут на 2 часа 14 минут."));

        ApiClient.Result route = ApiClient.routeFromJson(degraded, "moscow");
        String message = RouteChatPresentation.routeMessage(route);

        assertTrue(message.contains("Маршрут сокращён"));
        assertTrue(message.contains("Вы просили 6 часов"));
        assertTrue(message.contains("2 часа 14 минут"));
        assertFalse(message.startsWith("Готово!"));
    }

    @Test public void snapshotRoundTripKeepsFullChildrenAndMissingCoordinates() throws Exception {
        ApiClient.Result source = ApiClient.routeFromJson(freeRoamRoute(), "moscow");
        ApiClient.Result restored = ApiClient.routeFromSnapshot(ApiClient.routeSnapshot(source));
        assertNotNull(restored);
        assertEquals(3, restored.routeGroups.get(0).children.size());
        assertEquals("No coordinates", restored.routeGroups.get(0).children.get(2).name);
        assertFalse(restored.routeGroups.get(0).children.get(2).hasCoordinates());
        assertTrue(restored.routeGroups.get(0).hasVisitZone);
        assertEquals(1, restored.legGeometries.size());
    }

    @Test public void incompleteGroupedSnapshotForcesReload() throws Exception {
        JSONObject snapshot = new JSONObject()
                .put("routeId", "r").put("routeVersion", 1).put("routeGroupsEnabled", true)
                .put("points", new JSONArray()).put("path", new JSONArray());
        assertNull(ApiClient.routeFromSnapshot(snapshot.toString()));
    }

    @Test public void listIsCollapsedByDefaultAndExpansionDoesNotHideNextStop() throws Exception {
        ApiClient.Result route = ApiClient.routeFromJson(freeRoamRoute(), "moscow");
        List<RouteGroupSupport.DisplayRow> collapsed = RouteGroupSupport.displayRows(
                route, Collections.emptySet());
        assertEquals(2, collapsed.size());
        assertFalse(collapsed.get(0).isChild());
        assertTrue(collapsed.get(0).hasChildren);
        assertEquals("Next logical stop", collapsed.get(1).point.name);

        Set<Integer> expanded = new HashSet<>(Collections.singletonList(1));
        List<RouteGroupSupport.DisplayRow> rows = RouteGroupSupport.displayRows(route, expanded);
        assertEquals(5, rows.size());
        assertTrue(rows.get(1).isChild());
        assertEquals("Child", rows.get(1).child.name);
        assertEquals("No coordinates", rows.get(3).child.name);
        assertEquals("Next logical stop", rows.get(4).point.name);
    }

    @Test public void multipleGroupsCanStayExpandedIndependently() throws Exception {
        ApiClient.Result route = ApiClient.routeFromJson(freeRoamRoute(), "moscow");
        route.routeGroups = Arrays.asList(route.routeGroups.get(0),
                new ApiClient.RouteGroup(2, "msk036",
                        Collections.singletonList(new ApiClient.RouteChild(
                                "msk099", null, "Another child", Double.NaN, Double.NaN,
                                "CONTAINS")), Collections.emptyList(), Collections.emptyList(),
                        false));
        Set<Integer> expanded = new HashSet<>(Arrays.asList(1, 2));
        List<RouteGroupSupport.DisplayRow> rows = RouteGroupSupport.displayRows(route, expanded);
        assertEquals(6, rows.size());
        assertEquals("Another child", rows.get(5).child.name);
    }

    @Test public void viewModelKeepsExpansionAcrossGpsDrivenRenders() throws Exception {
        MapActivity.RouteViewModel model = new MapActivity.RouteViewModel();
        model.expandedGroupOrders.add(1);
        ApiClient.Result route = ApiClient.routeFromJson(freeRoamRoute(), "moscow");
        String before = VisitingPresentation.pointListRenderKey(
                route, 1, model.expandedGroupOrders);

        model.walk = walk(1, "VISITING");
        String afterGps = VisitingPresentation.pointListRenderKey(
                route, model.walk.currentPointOrder, model.expandedGroupOrders);

        assertEquals(before, afterGps);
        assertEquals(Collections.singleton(1), model.expandedGroupOrders);
    }

    @Test public void childMarkersExistOnlyWhileVisitingCurrentParent() throws Exception {
        ApiClient.Result route = ApiClient.routeFromJson(freeRoamRoute(), "moscow");
        ApiClient.WalkResult moving = walk(1, "MOVING");
        ApiClient.WalkResult visiting = walk(1, "VISITING");
        ApiClient.WalkResult next = walk(2, "VISITING");

        assertTrue(RouteGroupSupport.visibleChildMarkers(route, moving).isEmpty());
        List<ApiClient.RouteChild> markers = RouteGroupSupport.visibleChildMarkers(route, visiting);
        assertEquals(2, markers.size());
        assertEquals("child", markers.get(0).placeId);
        assertTrue(RouteGroupSupport.visibleChildMarkers(route, next).isEmpty());
    }

    @Test public void markersDeduplicateParentButKeepDistinctColocatedChildren() throws Exception {
        ApiClient.Result route = ApiClient.routeFromJson(freeRoamRoute(), "moscow");
        ApiClient.RouteGroup original = route.routeGroups.get(0);
        route.routeGroups = Collections.singletonList(new ApiClient.RouteGroup(
                1, original.catalogId, Arrays.asList(
                        new ApiClient.RouteChild("msk005", "parent-copy", "Parent copy",
                                55.75, 37.61, "CONTAINS"),
                        new ApiClient.RouteChild("msk080", "same-a", "Same A",
                                55.753, 37.619, "CONTAINS"),
                        new ApiClient.RouteChild("msk081", "same-b", "Same B",
                                55.753, 37.619, "CLUSTER_MEMBER")),
                Collections.emptyList(), Collections.emptyList(), true));

        List<ApiClient.RouteChild> markers = RouteGroupSupport.visibleChildMarkers(
                route, walk(1, "VISITING"));
        assertEquals(2, markers.size());
        assertEquals("Same A", markers.get(0).name);
        assertEquals("Same B", markers.get(1).name);
    }

    @Test public void externalLegGeometryIsDrawnWithoutInternalChildSegments() throws Exception {
        ApiClient.Result route = ApiClient.routeFromJson(freeRoamRoute(), "moscow");
        assertEquals(1, RouteGroupSupport.drawableSegments(route).size());
        assertEquals(2, RouteGroupSupport.drawableSegments(route).get(0).size());
    }

    @Test public void groupWithoutGeoJsonUsesParentPointFallback() throws Exception {
        ApiClient.Result route = ApiClient.routeFromJson(freeRoamRoute(), "moscow");
        ApiClient.WalkResult visiting = walk(1, "VISITING");
        assertEquals(-1, RouteGroupSupport.boundaryDistance(route, visiting, 2500));
        route.routeGroups = Collections.singletonList(new ApiClient.RouteGroup(
                1, "msk005", route.routeGroups.get(0).children,
                Collections.emptyList(), Collections.emptyList(), false));
        assertEquals(2500, RouteGroupSupport.boundaryDistance(route, visiting, 2500));
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

    private static ApiClient.WalkResult walk(int pointOrder, String phase) {
        return new ApiClient.WalkResult(true, "", "w", "ACTIVE", pointOrder,
                10, false, 0, null, 0, phase, 30, false);
    }

    private static JSONObject baseRoute() throws Exception {
        return new JSONObject().put("routeId", "r").put("routeVersion", 1)
                .put("totalMinutes", 20).put("query", "walk")
                .put("searchArea", new JSONObject().put("label", "center"))
                .put("points", new JSONArray()
                        .put(new JSONObject().put("placeId", "parent")
                                .put("catalogId", "msk005").put("name", "Parent")
                                .put("lat", 55.75).put("lon", 37.61).put("visitMinutes", 20))
                        .put(new JSONObject().put("placeId", "next")
                                .put("catalogId", "msk036").put("name", "Next logical stop")
                                .put("lat", 55.83).put("lon", 37.63).put("visitMinutes", 20)))
                .put("legs", new JSONArray().put(new JSONObject().put("toOrder", 1)
                        .put("distanceMeters", 100).put("durationSeconds", 80)
                        .put("geometry", new JSONArray()
                                .put(new JSONArray().put(37.60).put(55.74))
                                .put(new JSONArray().put(37.61).put(55.75)))));
    }

    private static JSONObject freeRoamRoute() throws Exception {
        JSONArray children = new JSONArray()
                .put(child("msk050", "child", "Child", 55.751, 37.617, "CONTAINS"))
                .put(child("msk051", "child2", "Child 2", 55.752, 37.618,
                        "CLUSTER_MEMBER"))
                .put(child("msk052", null, "No coordinates", null, null, "CONTAINS"));
        return baseRoute().put("routeGroupsEnabled", true)
                .put("routeGroups", new JSONArray().put(new JSONObject()
                        .put("pointOrder", 1).put("catalogId", "msk005")
                        .put("children", children)
                        .put("waypoints", new JSONArray()).put("waypointLegs", new JSONArray())
                        .put("visitZone", new JSONObject().put("type", "Polygon")
                                .put("coordinates", new JSONArray()))));
    }

    private static JSONObject child(String catalogId, String placeId, String name,
                                    Double lat, Double lon, String relation) throws Exception {
        return new JSONObject().put("catalogId", catalogId)
                .put("placeId", placeId == null ? JSONObject.NULL : placeId)
                .put("name", name).put("lat", lat == null ? JSONObject.NULL : lat)
                .put("lon", lon == null ? JSONObject.NULL : lon).put("relation", relation);
    }
}
