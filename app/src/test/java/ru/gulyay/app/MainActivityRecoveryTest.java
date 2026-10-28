package ru.gulyay.app;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

import java.io.EOFException;
import java.net.SocketTimeoutException;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public class MainActivityRecoveryTest {
    @Test public void timeoutOrServerErrorKeepsLastConfirmedRouteState() {
        assertEquals(RouteLifecycleRecovery.HistoryRouteState.UNCONFIRMED,
                RouteLifecycleRecovery.fromRouteLookup(false, false, null));
        assertFalse(RouteLifecycleRecovery.shouldReplaceHistoryCards(false, 3, 3));
    }

    @Test public void onlyRouteScopedNotFoundMeansRouteWasRemoved() {
        assertEquals(RouteLifecycleRecovery.HistoryRouteState.REMOVED,
                RouteLifecycleRecovery.fromRouteLookup(true, false, null));
    }

    @Test public void routeOutsideThreeItemHistoryRemainsReadyWhenFound() {
        assertEquals(RouteLifecycleRecovery.HistoryRouteState.READY,
                RouteLifecycleRecovery.fromRouteLookup(true, true, null));
    }

    @Test public void routeWithoutWalkRestoresAsReady() {
        assertEquals(RouteLifecycleRecovery.HistoryRouteState.READY,
                RouteLifecycleRecovery.fromRouteLookup(true, true, null));
    }

    @Test public void stoppedAndCompletedRoutesNeverRestoreAsReady() {
        assertEquals(RouteLifecycleRecovery.HistoryRouteState.TERMINAL,
                RouteLifecycleRecovery.fromRouteLookup(true, true, "STOPPED"));
        assertEquals(RouteLifecycleRecovery.HistoryRouteState.TERMINAL,
                RouteLifecycleRecovery.fromRouteLookup(true, true, "COMPLETED"));
    }

    @Test public void staleHistoryResponseIsRejected() {
        assertFalse(RouteLifecycleRecovery.isCurrentHistoryResponse(4, 5));
        assertTrue(RouteLifecycleRecovery.isCurrentHistoryResponse(5, 5));
        assertFalse(RouteLifecycleRecovery.shouldReplaceHistoryCards(true, 4, 5));
    }

    @Test public void staleRouteStateResponseCannotApplyAfterRouteSwitch() {
        assertFalse(RouteLifecycleRecovery.isCurrentRouteStateRequest("route-a", 7,
                "route-b", 8));
        assertFalse(RouteLifecycleRecovery.isCurrentRouteStateRequest("route-a", 7,
                "route-a", 8));
        assertTrue(RouteLifecycleRecovery.isCurrentRouteStateRequest("route-a", 8,
                "route-a", 8));
    }

    @Test public void historyStatusLabelsPreserveEveryBackendState() {
        assertEquals("Маршрут готов", RouteLifecycleRecovery.historyStatusLabel(null));
        assertEquals("Прогулка идёт", RouteLifecycleRecovery.historyStatusLabel("ACTIVE"));
        assertEquals("Прогулка на паузе", RouteLifecycleRecovery.historyStatusLabel("PAUSED"));
        assertEquals("Прогулка остановлена", RouteLifecycleRecovery.historyStatusLabel("STOPPED"));
        assertEquals("Маршрут пройден", RouteLifecycleRecovery.historyStatusLabel("COMPLETED"));
    }

    @Test public void activeAndPausedHistoryRoutesCannotBeDeleted() {
        assertFalse(RouteLifecycleRecovery.canDeleteHistoryRoute("ACTIVE"));
        assertFalse(RouteLifecycleRecovery.canDeleteHistoryRoute("PAUSED"));
        assertTrue(RouteLifecycleRecovery.canDeleteHistoryRoute(null));
        assertTrue(RouteLifecycleRecovery.canDeleteHistoryRoute("STOPPED"));
        assertTrue(RouteLifecycleRecovery.canDeleteHistoryRoute("COMPLETED"));
    }

    @Test public void offlineSnapshotRequiresMatchingRouteVersionAndCurrentBootWindow() {
        long savedAt = 1_000L;
        long expiresAt = savedAt + RouteSnapshotPolicy.OFFLINE_VIEW_WINDOW_MILLIS;
        assertTrue(RouteSnapshotPolicy.isValidForOfflineView("route-a", 2, savedAt, expiresAt,
                "route-a", 2, savedAt + 1));
        assertFalse(RouteSnapshotPolicy.isValidForOfflineView("route-b", 2, savedAt, expiresAt,
                "route-a", 2, savedAt + 1));
        assertFalse(RouteSnapshotPolicy.isValidForOfflineView("route-a", 1, savedAt, expiresAt,
                "route-a", 2, savedAt + 1));
        assertFalse(RouteSnapshotPolicy.isValidForOfflineView("route-a", 2, savedAt, expiresAt,
                "route-a", 2, expiresAt + 1));
        assertFalse(RouteSnapshotPolicy.isValidForOfflineView("route-a", 2, savedAt, expiresAt,
                "route-a", 2, savedAt - 1));
    }

    @Test public void unconfirmedRouteCardOpensSnapshotOnlyAfterFailedSync() {
        assertTrue(RouteLifecycleRecovery.canOpenUnconfirmedSnapshotAfterSyncFailure(
                false, true, true, true));
        assertFalse(RouteLifecycleRecovery.canOpenUnconfirmedSnapshotAfterSyncFailure(
                false, true, false, true));
        assertFalse(RouteLifecycleRecovery.canOpenUnconfirmedSnapshotAfterSyncFailure(
                false, true, true, false));
        assertFalse(RouteLifecycleRecovery.canOpenUnconfirmedSnapshotAfterSyncFailure(
                false, false, true, true));
        assertFalse(RouteLifecycleRecovery.canOpenUnconfirmedSnapshotAfterSyncFailure(
                true, true, true, true));
    }

    @Test public void releasedMapViewCallbackCannotChangeCurrentMap() {
        Object oldMapView = new Object();
        Object currentMapView = new Object();
        assertFalse(MapLifecycleGuard.shouldApplyMapCallback(oldMapView, currentMapView,
                true, true));
        assertFalse(MapLifecycleGuard.shouldApplyMapCallback(currentMapView, currentMapView,
                false, true));
        assertFalse(MapLifecycleGuard.shouldApplyMapCallback(currentMapView, currentMapView,
                true, false));
        assertTrue(MapLifecycleGuard.shouldApplyMapCallback(currentMapView, currentMapView,
                true, true));
    }

    @Test public void etaAtTargetDoesNotJumpToEndOfRoute() {
        List<WalkGuidanceMath.Point> leg = Arrays.asList(
                new WalkGuidanceMath.Point(55.7600, 37.6100),
                new WalkGuidanceMath.Point(55.7605, 37.6150),
                new WalkGuidanceMath.Point(55.7608, 37.6180));
        WalkGuidanceMath.Result result = WalkGuidanceMath.remainingOnLeg(
                leg, 55.7608, 37.6180, 0);
        assertEquals(2, result.nearestIndex);
        assertTrue(result.distanceMeters <= 1);
    }

    @Test public void loopIntersectionUsesCurrentProgressFloor() {
        List<WalkGuidanceMath.Point> leg = Arrays.asList(
                new WalkGuidanceMath.Point(55.0, 37.0),
                new WalkGuidanceMath.Point(55.0, 37.001),
                new WalkGuidanceMath.Point(55.001, 37.001),
                new WalkGuidanceMath.Point(55.001, 37.0),
                new WalkGuidanceMath.Point(55.0, 37.001),
                new WalkGuidanceMath.Point(55.0, 37.002));
        WalkGuidanceMath.Result beforeLoop = WalkGuidanceMath.remainingOnLeg(
                leg, 55.0, 37.001, 0);
        WalkGuidanceMath.Result afterLoop = WalkGuidanceMath.remainingOnLeg(
                leg, 55.0, 37.001, 3);
        assertEquals(1, beforeLoop.nearestIndex);
        assertEquals(4, afterLoop.nearestIndex);
        assertTrue(beforeLoop.distanceMeters > afterLoop.distanceMeters);
    }

    @Test public void stationaryFreshMeasurementsRemainEligibleWithoutMovement() {
        assertEquals(12_000L, PositionSubmissionPolicy.LOCATION_UPDATE_INTERVAL_MILLIS);
        assertTrue(PositionSubmissionPolicy.isFresh(10_000L, 10_000L, 0L));
        assertTrue(PositionSubmissionPolicy.isFresh(15_000L, 15_000L, 10_000L));
        assertFalse(PositionSubmissionPolicy.isFresh(10_000L, 15_000L, 10_000L));
        assertFalse(PositionSubmissionPolicy.isFresh(10_000L, 45_001L, 0L));
    }

    @Test public void positionPolicyAllowsTwoThenWaitsForRollingWindow() {
        assertEquals(0L, PositionSubmissionPolicy.delayUntilSlot(10_000L, 0L, 0L));
        assertEquals(5_000L,
                PositionSubmissionPolicy.delayUntilSlot(10_000L, 0L, 10_000L));
        assertEquals(55_000L,
                PositionSubmissionPolicy.delayUntilSlot(15_000L, 10_000L, 15_000L));
        assertEquals(0L,
                PositionSubmissionPolicy.delayUntilSlot(70_000L, 10_000L, 15_000L));
    }

    @Test public void visitStopwatchCountsUpAndFreezesWhilePaused() {
        assertEquals(0, VisitStopwatch.elapsedSeconds(0, 10_000L, 10_999L, true));
        assertEquals(5, VisitStopwatch.elapsedSeconds(0, 10_000L, 15_000L, true));
        assertEquals(65, VisitStopwatch.elapsedSeconds(60, 10_000L, 15_000L, true));
        assertEquals(60, VisitStopwatch.elapsedSeconds(60, 10_000L, 25_000L, false));
        assertEquals("00:00", VisitStopwatch.format(0));
        assertEquals("00:33", VisitStopwatch.format(33));
        assertEquals("01:05", VisitStopwatch.format(65));
        assertEquals("18:42", VisitStopwatch.format(1122));
        assertEquals("59:59", VisitStopwatch.format(3599));
        assertEquals("1:00:00", VisitStopwatch.format(3600));
        assertEquals("1:01:01", VisitStopwatch.format(3661));
        assertEquals("1:22:16", VisitStopwatch.format(4936));
        assertEquals("12:34:56", VisitStopwatch.format(45296));
    }

    @Test public void routeReadRetriesOneTransientTransportFailureOnly() {
        assertTrue(RouteLoadRetryPolicy.shouldRetry(new EOFException(), 0));
        assertTrue(RouteLoadRetryPolicy.shouldRetry(new SocketTimeoutException(), 0));
        assertFalse(RouteLoadRetryPolicy.shouldRetry(new EOFException(), 1));
        assertFalse(RouteLoadRetryPolicy.shouldRetry(new IllegalStateException(), 0));
        assertTrue(RouteLoadRetryPolicy.shouldRetryHttp(0));
        assertFalse(RouteLoadRetryPolicy.shouldRetryHttp(1));
    }

    @Test public void routeReadActuallyRetriesAfterEof() throws Exception {
        AtomicInteger calls = new AtomicInteger();
        String result = RouteLoadRetryPolicy.execute(() -> {
            if (calls.getAndIncrement() == 0) throw new EOFException();
            return "route";
        }, value -> false);
        assertEquals("route", result);
        assertEquals(2, calls.get());
    }

    @Test public void visitingPresentationUsesCurrentPointAndRealNextLeg() {
        ApiClient.Result route = visitingRoute();
        ApiClient.WalkResult walk = new ApiClient.WalkResult(true, "", "walk", "ACTIVE",
                1, 30, true, 0, null, 0, "VISITING", 1122, false);

        VisitingPresentation.Model model = VisitingPresentation.from(route, walk, 1122, null);

        assertEquals("Точка 1 из 3", model.pointLabel);
        assertEquals("Очень длинное название текущей локации", model.pointName);
        assertEquals("18:42", model.stopwatch);
        assertEquals("Далее: Красная площадь", model.nextTitle);
        assertEquals("261 м · 4 мин пешком", model.nextMeta);
        assertTrue(model.showNext);
        assertFalse(VisitingPresentation.shouldShowPartnerOffer(model.partnerOffer));
        assertEquals("Фото", VisitingPresentation.PHOTO_PLACEHOLDER);
    }

    @Test public void visitingPresentationHidesNextAndPartnerAtLastPoint() {
        ApiClient.Result route = visitingRoute();
        ApiClient.WalkResult walk = new ApiClient.WalkResult(true, "", "walk", "PAUSED",
                3, 0, false, 0, null, 0, "VISITING", 65, false);

        VisitingPresentation.Model model = VisitingPresentation.from(route, walk, 65, null);

        assertEquals("Точка 3 из 3", model.pointLabel);
        assertEquals("01:05", model.stopwatch);
        assertFalse(model.showNext);
        assertEquals("", model.nextTitle);
        assertEquals("", model.nextMeta);
        assertFalse(VisitingPresentation.shouldShowPartnerOffer(null));
        assertTrue(VisitingPresentation.shouldShowPartnerOffer(
                new VisitingPresentation.PartnerOffer(
                        "Зайти за кофе?", "Без скидок", "Cofix на Тверской",
                        "COFFEE", 6, "Партнёр рядом", "ADD_TO_ROUTE",
                        "Добавить в маршрут")));
        assertTrue(VisitingPresentation.shouldShowRemainingPoints(true));
        assertTrue(VisitingPresentation.shouldShowRemainingPoints(false));
    }

    @Test public void partnerOfferRequiresInsertActionAndConfirmedFields() {
        ApiClient.PartnerOffer apiOffer = new ApiClient.PartnerOffer(
                "offer", "cofix", "branch-1", "Зайти за кофе?", "Без скидок",
                "Cofix", "COFFEE", 4, true, "ADD_TO_ROUTE", "Добавить в маршрут");
        VisitingPresentation.PartnerOffer offer = VisitingPresentation.PartnerOffer.from(apiOffer);
        assertTrue(VisitingPresentation.shouldShowPartnerOffer(offer));
        assertFalse(VisitingPresentation.shouldShowPartnerOffer(
                new VisitingPresentation.PartnerOffer(
                        "Зайти", "", "Cofix", "COFFEE", 4, "Партнёр рядом",
                        "OPEN_DGIS", "Открыть")));
        VisitingPresentation.PartnerOffer preview =
                VisitingPresentation.PartnerOffer.from(new ApiClient.PartnerOffer(
                        "preview", "drinkit", "branch-1", "Зайти", "Не реклама",
                        "Дринкит", "COFFEE", 4, false, "ADD_TO_ROUTE",
                        "Добавить в маршрут"));
        assertTrue(VisitingPresentation.shouldShowPartnerOffer(preview));
        assertEquals("Рядом по пути", preview.disclosure);
    }

    @Test public void stalePartnerOfferResponseCannotCrossPointOrWalkState() {
        String key = PartnerOfferRequestPolicy.key("walk", 1);
        assertTrue(PartnerOfferRequestPolicy.isCurrent(
                key, 3, "walk", "ACTIVE", "VISITING", 1, 3));
        assertFalse(PartnerOfferRequestPolicy.isCurrent(
                key, 3, "walk", "ACTIVE", "VISITING", 2, 3));
        assertFalse(PartnerOfferRequestPolicy.isCurrent(
                key, 3, "walk", "PAUSED", "VISITING", 1, 3));
        assertFalse(PartnerOfferRequestPolicy.isCurrent(
                key, 3, "walk", "ACTIVE", "MOVING", 1, 3));
        assertFalse(PartnerOfferRequestPolicy.isCurrent(
                key, 3, "walk", "ACTIVE", "VISITING", 1, 4));
    }

    @Test public void missingPartnerOfferRetriesOnlyAfterFreshMinuteSlot() {
        String key = PartnerOfferRequestPolicy.key("walk", 1);
        assertTrue(PartnerOfferRequestPolicy.shouldRequest(key, null, false, 1_000L, 0L));
        assertFalse(PartnerOfferRequestPolicy.shouldRequest(key, key, false, 60_999L, 1_000L));
        assertTrue(PartnerOfferRequestPolicy.shouldRequest(key, key, false, 61_000L, 1_000L));
        assertFalse(PartnerOfferRequestPolicy.shouldRequest(key, key, true, 120_000L, 1_000L));
        assertTrue(PartnerOfferRequestPolicy.shouldRequest(
                PartnerOfferRequestPolicy.key("walk", 2), key, false, 2_000L, 1_000L));
    }

    @Test public void visitingPointListOnlyRendersWhenItsStructureChanges() {
        ApiClient.Result route = visitingRoute();
        String initial = VisitingPresentation.pointListRenderKey(route, 1, true);

        assertEquals(initial, VisitingPresentation.pointListRenderKey(route, 1, true));
        assertFalse(initial.equals(VisitingPresentation.pointListRenderKey(route, 2, true)));
        assertFalse(initial.equals(VisitingPresentation.pointListRenderKey(route, 1, false)));

        ApiClient.WalkResult active = new ApiClient.WalkResult(true, "", "walk", "ACTIVE",
                1, 30, true, 0, null, 0, "VISITING", 33, false);
        ApiClient.WalkResult gpsRefresh = new ApiClient.WalkResult(true, "", "walk", "ACTIVE",
                1, 29, false, 80, null, 0, "VISITING", 34, false);
        ApiClient.WalkResult nextVisit = new ApiClient.WalkResult(true, "", "walk", "ACTIVE",
                2, 20, true, 0, null, 0, "VISITING", 0, false);

        assertEquals(VisitingPresentation.structureRenderKey(route, active),
                VisitingPresentation.structureRenderKey(route, gpsRefresh));
        assertFalse(VisitingPresentation.structureRenderKey(route, active).equals(
                VisitingPresentation.structureRenderKey(route, nextVisit)));
    }

    private static ApiClient.Result visitingRoute() {
        List<ApiClient.PlaceOption> points = Arrays.asList(
                new ApiClient.PlaceOption("one",
                        "Очень длинное название текущей локации", false),
                new ApiClient.PlaceOption("two", "Красная площадь", false),
                new ApiClient.PlaceOption("three", "Музей", false));
        ApiClient.Result route = new ApiClient.Result(true, "", "route", 1,
                0, null, points, Collections.emptyList());
        route.legGeometries = Arrays.asList(
                new ApiClient.RouteLegGeometry(1, 120, 100, Collections.emptyList()),
                new ApiClient.RouteLegGeometry(2, 261, 240, Collections.emptyList()),
                new ApiClient.RouteLegGeometry(3, 500, 420, Collections.emptyList()));
        return route;
    }
}
