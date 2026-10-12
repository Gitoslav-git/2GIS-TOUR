package ru.gulyay.app;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

import java.util.Arrays;
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

    @Test public void unconfirmedRouteCardOpensOnlyAValidSnapshotReadOnly() {
        assertTrue(RouteLifecycleRecovery.canOpenUnconfirmedSnapshot(false, true));
        assertFalse(RouteLifecycleRecovery.canOpenUnconfirmedSnapshot(false, false));
        assertFalse(RouteLifecycleRecovery.canOpenUnconfirmedSnapshot(true, true));
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
}
