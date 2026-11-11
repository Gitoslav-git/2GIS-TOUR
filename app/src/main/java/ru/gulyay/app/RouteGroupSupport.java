package ru.gulyay.app;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/** Pure group presentation/navigation rules; never mutates backend walk state. */
final class RouteGroupSupport {
    static final class DisplayRow {
        final int pointOrder;
        final ApiClient.PlaceOption point;
        final ApiClient.RouteWaypoint waypoint;
        final boolean activeWaypoint;

        private DisplayRow(int pointOrder, ApiClient.PlaceOption point,
                           ApiClient.RouteWaypoint waypoint, boolean activeWaypoint) {
            this.pointOrder = pointOrder;
            this.point = point;
            this.waypoint = waypoint;
            this.activeWaypoint = activeWaypoint;
        }

        static DisplayRow point(int pointOrder, ApiClient.PlaceOption point) {
            return new DisplayRow(pointOrder, point, null, false);
        }

        static DisplayRow waypoint(int pointOrder, ApiClient.RouteWaypoint waypoint,
                                   boolean activeWaypoint) {
            return new DisplayRow(pointOrder, null, waypoint, activeWaypoint);
        }

        boolean isWaypoint() { return waypoint != null; }
    }

    static final class NavigationTarget {
        final ApiClient.RouteWaypoint waypoint;
        final ApiClient.RouteWaypointLeg leg;
        final int legIndex;
        final int pathIndex;
        final int remainingMeters;

        NavigationTarget(ApiClient.RouteWaypoint waypoint, ApiClient.RouteWaypointLeg leg,
                         int legIndex, int pathIndex, int remainingMeters) {
            this.waypoint = waypoint; this.leg = leg; this.legIndex = legIndex;
            this.pathIndex = pathIndex; this.remainingMeters = remainingMeters;
        }
    }

    private RouteGroupSupport() { }

    static ApiClient.RouteGroup groupForPoint(ApiClient.Result route, int pointOrder) {
        if (route == null || route.routeGroups == null) return null;
        for (ApiClient.RouteGroup group : route.routeGroups) {
            if (group.pointOrder == pointOrder && !group.waypoints.isEmpty()) return group;
        }
        return null;
    }

    static boolean hasActiveGroup(ApiClient.Result route, ApiClient.WalkResult walk) {
        return walk != null && groupForPoint(route, walk.currentPointOrder) != null;
    }

    static List<DisplayRow> displayRows(ApiClient.Result route, int currentPointOrder,
                                        int activeWaypointOrder) {
        List<DisplayRow> rows = new ArrayList<>();
        if (route == null || route.points == null) return rows;
        int startIndex = currentPointOrder > 0
                ? Math.min(currentPointOrder - 1, route.points.size()) : 0;
        for (int index = startIndex; index < route.points.size(); index++) {
            int pointOrder = index + 1;
            ApiClient.PlaceOption point = route.points.get(index);
            rows.add(DisplayRow.point(pointOrder, point));
            ApiClient.RouteGroup group = groupForPoint(route, pointOrder);
            if (group == null) continue;
            for (ApiClient.RouteWaypoint waypoint : group.waypoints) {
                if (sameLogicalPoint(point, waypoint)) continue;
                rows.add(DisplayRow.waypoint(pointOrder, waypoint,
                        pointOrder == currentPointOrder
                                && waypoint.order == activeWaypointOrder));
            }
        }
        return rows;
    }

    private static boolean sameLogicalPoint(ApiClient.PlaceOption point,
                                            ApiClient.RouteWaypoint waypoint) {
        if (point.placeId != null && point.placeId.equals(waypoint.placeId)) return true;
        if (point.catalogId != null && point.catalogId.equals(waypoint.catalogId)) return true;
        return Double.isFinite(point.lat) && Double.isFinite(point.lon)
                && Math.abs(point.lat - waypoint.lat) < 0.000001
                && Math.abs(point.lon - waypoint.lon) < 0.000001;
    }

    static List<ApiClient.RouteWaypoint> uniqueChildMarkers(ApiClient.Result route) {
        List<ApiClient.RouteWaypoint> result = new ArrayList<>();
        if (route == null || route.routeGroups == null) return result;
        Set<String> seen = new HashSet<>();
        for (ApiClient.PlaceOption parent : route.points) {
            if (parent.placeId != null) seen.add("id:" + parent.placeId);
            if (Double.isFinite(parent.lat) && Double.isFinite(parent.lon)) {
                seen.add(coordinateKey(parent.lat, parent.lon));
            }
        }
        for (ApiClient.RouteGroup group : route.routeGroups) {
            for (ApiClient.RouteWaypoint waypoint : group.waypoints) {
                String idKey = waypoint.placeId == null ? null : "id:" + waypoint.placeId;
                String coordinateKey = coordinateKey(waypoint.lat, waypoint.lon);
                if ((idKey != null && seen.contains(idKey)) || seen.contains(coordinateKey)) continue;
                if (idKey != null) seen.add(idKey);
                seen.add(coordinateKey);
                result.add(waypoint);
            }
        }
        return result;
    }

    static List<List<ApiClient.GeoCoordinate>> realGeometrySegments(ApiClient.Result route) {
        List<List<ApiClient.GeoCoordinate>> result = new ArrayList<>();
        if (route == null || route.routeGroups == null) return result;
        for (ApiClient.RouteGroup group : route.routeGroups) {
            for (ApiClient.RouteWaypointLeg leg : group.waypointLegs) {
                if (leg.path != null && leg.path.size() >= 2) result.add(leg.path);
            }
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
        result.addAll(realGeometrySegments(route));
        return result;
    }

    static int boundaryDistance(ApiClient.Result route, ApiClient.WalkResult walk,
                                int localParentDistance) {
        // A grouped visit is bounded by server-owned GeoJSON. Neither distance to the
        // parent marker nor the previous response's distance describes the new GPS fix.
        if (hasActiveGroup(route, walk)) return -1;
        return localParentDistance;
    }

    static NavigationTarget navigationTarget(ApiClient.RouteGroup group, double lat, double lon,
                                             int previousLegIndex, int previousPathIndex) {
        if (group == null || group.waypointLegs.isEmpty() || group.waypoints.isEmpty()) return null;
        int floor = Math.max(0, Math.min(previousLegIndex, group.waypointLegs.size() - 1));
        int chosen = floor;
        int chosenIndex = previousPathIndex;
        int chosenRemaining = Integer.MAX_VALUE;
        double bestProximity = Double.MAX_VALUE;
        for (int index = floor; index < group.waypointLegs.size(); index++) {
            ApiClient.RouteWaypointLeg leg = group.waypointLegs.get(index);
            if (leg.path == null || leg.path.isEmpty()) continue;
            List<WalkGuidanceMath.Point> path = guidancePath(leg.path);
            int pathFloor = index == floor ? previousPathIndex : 0;
            WalkGuidanceMath.Result progress = WalkGuidanceMath.remainingOnLeg(
                    path, lat, lon, pathFloor);
            ApiClient.GeoCoordinate nearest = leg.path.get(progress.nearestIndex);
            double proximity = WalkGuidanceMath.meters(lat, lon, nearest.lat, nearest.lon);
            if (proximity < bestProximity) {
                bestProximity = proximity; chosen = index;
                chosenIndex = progress.nearestIndex; chosenRemaining = progress.distanceMeters;
            }
        }
        if (chosenRemaining <= 35 && chosen + 1 < group.waypointLegs.size()) {
            chosen++; chosenIndex = 0;
            WalkGuidanceMath.Result next = WalkGuidanceMath.remainingOnLeg(
                    guidancePath(group.waypointLegs.get(chosen).path), lat, lon, 0);
            chosenRemaining = next.distanceMeters; chosenIndex = next.nearestIndex;
        }
        ApiClient.RouteWaypointLeg leg = group.waypointLegs.get(chosen);
        ApiClient.RouteWaypoint waypoint = waypointForOrder(group, leg.toWaypointOrder);
        if (waypoint == null) waypoint = group.waypoints.get(Math.min(chosen, group.waypoints.size() - 1));
        return new NavigationTarget(waypoint, leg, chosen, chosenIndex, chosenRemaining);
    }

    private static ApiClient.RouteWaypoint waypointForOrder(ApiClient.RouteGroup group, int order) {
        for (ApiClient.RouteWaypoint waypoint : group.waypoints) if (waypoint.order == order) return waypoint;
        return null;
    }

    private static List<WalkGuidanceMath.Point> guidancePath(List<ApiClient.GeoCoordinate> source) {
        List<WalkGuidanceMath.Point> result = new ArrayList<>(source.size());
        for (ApiClient.GeoCoordinate point : source) result.add(new WalkGuidanceMath.Point(point.lat, point.lon));
        return result;
    }

    private static String coordinateKey(double lat, double lon) {
        return String.format(java.util.Locale.US, "xy:%.6f:%.6f", lat, lon);
    }
}
