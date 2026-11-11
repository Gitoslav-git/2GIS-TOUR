package ru.gulyay.app;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/** Pure free-roam group presentation rules; never mutates backend walk state. */
final class RouteGroupSupport {
    static final class DisplayRow {
        final int pointOrder;
        final ApiClient.PlaceOption point;
        final ApiClient.RouteChild child;
        final boolean hasChildren;
        final boolean expanded;

        private DisplayRow(int pointOrder, ApiClient.PlaceOption point,
                           ApiClient.RouteChild child, boolean hasChildren,
                           boolean expanded) {
            this.pointOrder = pointOrder;
            this.point = point;
            this.child = child;
            this.hasChildren = hasChildren;
            this.expanded = expanded;
        }

        static DisplayRow point(int pointOrder, ApiClient.PlaceOption point,
                                boolean hasChildren, boolean expanded) {
            return new DisplayRow(pointOrder, point, null, hasChildren, expanded);
        }

        static DisplayRow child(int pointOrder, ApiClient.RouteChild child) {
            return new DisplayRow(pointOrder, null, child, false, false);
        }

        boolean isChild() { return child != null; }
    }

    private RouteGroupSupport() { }

    static ApiClient.RouteGroup groupForPoint(ApiClient.Result route, int pointOrder) {
        if (route == null || route.routeGroups == null) return null;
        for (ApiClient.RouteGroup group : route.routeGroups) {
            if (group.pointOrder == pointOrder && group.children != null
                    && !group.children.isEmpty()) return group;
        }
        return null;
    }

    static boolean hasActiveGroup(ApiClient.Result route, ApiClient.WalkResult walk) {
        return walk != null && groupForPoint(route, walk.currentPointOrder) != null;
    }

    static List<DisplayRow> displayRows(ApiClient.Result route, Set<Integer> expandedOrders) {
        List<DisplayRow> rows = new ArrayList<>();
        if (route == null || route.points == null) return rows;
        Set<Integer> expanded = expandedOrders == null ? new HashSet<>() : expandedOrders;
        for (int index = 0; index < route.points.size(); index++) {
            int pointOrder = index + 1;
            ApiClient.PlaceOption point = route.points.get(index);
            ApiClient.RouteGroup group = groupForPoint(route, pointOrder);
            boolean hasChildren = group != null;
            boolean isExpanded = hasChildren && expanded.contains(pointOrder);
            rows.add(DisplayRow.point(pointOrder, point, hasChildren, isExpanded));
            if (isExpanded) for (ApiClient.RouteChild child : group.children) {
                if (!sameLogicalPoint(point, child)) {
                    rows.add(DisplayRow.child(pointOrder, child));
                }
            }
        }
        return rows;
    }

    static List<ApiClient.RouteChild> visibleChildMarkers(ApiClient.Result route,
                                                          ApiClient.WalkResult walk) {
        List<ApiClient.RouteChild> result = new ArrayList<>();
        if (walk == null || !"VISITING".equals(walk.phase)) return result;
        ApiClient.RouteGroup group = groupForPoint(route, walk.currentPointOrder);
        if (group == null) return result;
        Set<String> parentKeys = new HashSet<>();
        if (route != null) for (ApiClient.PlaceOption parent : route.points) {
            if (parent.catalogId != null) parentKeys.add("catalog:" + parent.catalogId);
            if (parent.placeId != null) parentKeys.add("place:" + parent.placeId);
            if (Double.isFinite(parent.lat) && Double.isFinite(parent.lon)) {
                parentKeys.add(coordinateKey(parent.lat, parent.lon));
            }
        }
        Set<String> seenChildIds = new HashSet<>();
        for (ApiClient.RouteChild child : group.children) {
            if (!child.hasCoordinates()) continue;
            String catalogKey = child.catalogId == null ? null : "catalog:" + child.catalogId;
            String placeKey = child.placeId == null ? null : "place:" + child.placeId;
            String coordinate = coordinateKey(child.lat, child.lon);
            if ((catalogKey != null && (parentKeys.contains(catalogKey)
                    || seenChildIds.contains(catalogKey)))
                    || (placeKey != null && (parentKeys.contains(placeKey)
                    || seenChildIds.contains(placeKey)))
                    || parentKeys.contains(coordinate)) continue;
            if (catalogKey != null) seenChildIds.add(catalogKey);
            if (placeKey != null) seenChildIds.add(placeKey);
            result.add(child);
        }
        return result;
    }

    static List<List<ApiClient.GeoCoordinate>> drawableSegments(ApiClient.Result route) {
        List<List<ApiClient.GeoCoordinate>> result = new ArrayList<>();
        if (route == null) return result;
        if (route.legGeometries != null) {
            for (ApiClient.RouteLegGeometry leg : route.legGeometries) {
                if (leg.path != null && leg.path.size() >= 2) result.add(leg.path);
            }
        }
        if (result.isEmpty() && route.path != null && route.path.size() >= 2) {
            result.add(route.path);
        }
        return result;
    }

    static int boundaryDistance(ApiClient.Result route, ApiClient.WalkResult walk,
                                int localParentDistance) {
        ApiClient.RouteGroup group = walk == null ? null
                : groupForPoint(route, walk.currentPointOrder);
        return group != null && group.hasVisitZone ? -1 : localParentDistance;
    }

    static String childMarkerKey(ApiClient.Result route, ApiClient.WalkResult walk) {
        if (route == null || walk == null || !"VISITING".equals(walk.phase)) return "hidden";
        ApiClient.RouteGroup group = groupForPoint(route, walk.currentPointOrder);
        if (group == null) return "hidden";
        return route.routeVersion + ":" + walk.currentPointOrder + ":" + group.children.size();
    }

    private static boolean sameLogicalPoint(ApiClient.PlaceOption point,
                                            ApiClient.RouteChild child) {
        if (point.placeId != null && point.placeId.equals(child.placeId)) return true;
        if (point.catalogId != null && point.catalogId.equals(child.catalogId)) return true;
        return child.hasCoordinates() && Double.isFinite(point.lat) && Double.isFinite(point.lon)
                && Math.abs(point.lat - child.lat) < 0.000001
                && Math.abs(point.lon - child.lon) < 0.000001;
    }

    private static String coordinateKey(double lat, double lon) {
        return String.format(java.util.Locale.US, "xy:%.6f:%.6f", lat, lon);
    }
}
