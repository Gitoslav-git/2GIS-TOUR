package ru.gulyay.app;

import java.util.List;

/** Route-leg scoped navigation math, isolated for JVM regression tests. */
final class WalkGuidanceMath {
    static final class Point {
        final double lat;
        final double lon;

        Point(double lat, double lon) {
            this.lat = lat;
            this.lon = lon;
        }
    }

    static final class Result {
        final int nearestIndex;
        final int distanceMeters;

        Result(int nearestIndex, int distanceMeters) {
            this.nearestIndex = nearestIndex;
            this.distanceMeters = distanceMeters;
        }
    }

    private WalkGuidanceMath() { }

    static Result remainingOnLeg(List<Point> leg, double lat, double lon,
                                 int progressFloor) {
        if (leg == null || leg.isEmpty()) return new Result(0, -1);
        int start = Math.max(0, Math.min(progressFloor, leg.size() - 1));
        int nearest = start;
        double nearestDistance = Double.MAX_VALUE;
        for (int index = start; index < leg.size(); index++) {
            Point point = leg.get(index);
            double distance = meters(lat, lon, point.lat, point.lon);
            if (distance < nearestDistance) {
                nearestDistance = distance;
                nearest = index;
            }
        }
        double remaining = nearestDistance;
        for (int index = nearest; index + 1 < leg.size(); index++) {
            Point from = leg.get(index);
            Point to = leg.get(index + 1);
            remaining += meters(from.lat, from.lon, to.lat, to.lon);
        }
        return new Result(nearest, (int) Math.round(remaining));
    }

    static double meters(double lat1, double lon1, double lat2, double lon2) {
        double lat = Math.toRadians(lat2 - lat1);
        double lon = Math.toRadians(lon2 - lon1);
        double value = Math.sin(lat / 2) * Math.sin(lat / 2)
                + Math.cos(Math.toRadians(lat1)) * Math.cos(Math.toRadians(lat2))
                * Math.sin(lon / 2) * Math.sin(lon / 2);
        return 6_371_000 * 2 * Math.atan2(Math.sqrt(value), Math.sqrt(1 - value));
    }
}
