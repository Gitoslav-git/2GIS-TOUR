package ru.gulyay.app;

import java.util.Locale;

/** Pure VISITING presentation data; it never changes walk or GPS state. */
final class VisitingPresentation {
    static final String PHOTO_PLACEHOLDER = "Фото";

    static final class PartnerOffer {
        final String title;
        final String description;
        final String venueName;
        final int walkingMinutes;
        final String disclosure;
        final String actionLabel;
        final String actionUrl;

        PartnerOffer(String title, String description, String venueName,
                     int walkingMinutes, String disclosure,
                     String actionLabel, String actionUrl) {
            this.title = title;
            this.description = description;
            this.venueName = venueName;
            this.walkingMinutes = walkingMinutes;
            this.disclosure = disclosure;
            this.actionLabel = actionLabel;
            this.actionUrl = actionUrl;
        }

        static PartnerOffer from(ApiClient.PartnerOffer offer) {
            if (offer == null || !offer.commercial) return null;
            return new PartnerOffer(
                    offer.title, offer.description, offer.venueName,
                    offer.walkingMinutes, "Партнёрское предложение",
                    offer.actionLabel, offer.actionUrl);
        }
    }

    static final class Model {
        final String pointLabel;
        final String pointName;
        final String stopwatch;
        final String nextTitle;
        final String nextMeta;
        final boolean showNext;
        final PartnerOffer partnerOffer;

        Model(String pointLabel, String pointName, String stopwatch, String nextTitle,
              String nextMeta, boolean showNext, PartnerOffer partnerOffer) {
            this.pointLabel = pointLabel;
            this.pointName = pointName;
            this.stopwatch = stopwatch;
            this.nextTitle = nextTitle;
            this.nextMeta = nextMeta;
            this.showNext = showNext;
            this.partnerOffer = partnerOffer;
        }
    }

    private VisitingPresentation() { }

    static Model from(ApiClient.Result route, ApiClient.WalkResult walk, int elapsedSeconds,
                      PartnerOffer partnerOffer) {
        int total = route == null ? 0 : route.points.size();
        int order = walk == null ? 0 : walk.currentPointOrder;
        String pointName = "Локация";
        if (route != null && order > 0 && order <= total) {
            pointName = route.points.get(order - 1).name;
        }
        boolean showNext = route != null && order > 0 && order < total;
        String nextTitle = "";
        String nextMeta = "";
        if (showNext) {
            nextTitle = "Далее: " + route.points.get(order).name;
            ApiClient.RouteLegGeometry leg = nextLeg(route, order + 1);
            if (leg != null) nextMeta = formatLeg(leg.distanceMeters, leg.durationSeconds);
        }
        return new Model("Точка " + order + " из " + Math.max(order, total), pointName,
                VisitStopwatch.format(elapsedSeconds), nextTitle, nextMeta, showNext,
                partnerOffer);
    }

    static boolean shouldShowPartnerOffer(PartnerOffer offer) {
        return offer != null
                && present(offer.title)
                && present(offer.venueName)
                && offer.walkingMinutes > 0
                && present(offer.disclosure)
                && present(offer.actionLabel)
                && offer.actionUrl != null
                && offer.actionUrl.startsWith("https://2gis.ru/");
    }

    private static boolean present(String value) {
        return value != null && !value.trim().isEmpty();
    }

    static boolean shouldShowRemainingPoints(boolean compactScreen) {
        return true;
    }

    static String pointListRenderKey(ApiClient.Result route, int currentOrder,
                                     boolean nextPointAlreadyFeatured) {
        StringBuilder key = new StringBuilder()
                .append(currentOrder).append(':').append(nextPointAlreadyFeatured);
        if (route == null) return key.append(":no-route").toString();
        key.append(':').append(route.routeVersion).append(':').append(route.points.size());
        for (ApiClient.PlaceOption point : route.points) {
            key.append('|').append(point.placeId).append(':').append(point.name);
        }
        return key.toString();
    }

    static String structureRenderKey(ApiClient.Result route, ApiClient.WalkResult walk) {
        if (walk == null) return "no-walk";
        return pointListRenderKey(route, walk.currentPointOrder, true)
                + ':' + walk.phase;
    }

    private static ApiClient.RouteLegGeometry nextLeg(ApiClient.Result route, int toOrder) {
        if (route.legGeometries == null) return null;
        for (ApiClient.RouteLegGeometry leg : route.legGeometries) {
            if (leg.toOrder == toOrder) return leg;
        }
        return null;
    }

    private static String formatLeg(int distanceMeters, int durationSeconds) {
        String distance = distanceMeters > 0
                ? String.format(Locale.US, "%d м", distanceMeters) : "";
        String duration = durationSeconds > 0
                ? Math.max(1, (int) Math.ceil(durationSeconds / 60.0)) + " мин пешком" : "";
        if (!distance.isEmpty() && !duration.isEmpty()) return distance + " · " + duration;
        return distance.isEmpty() ? duration : distance;
    }
}
