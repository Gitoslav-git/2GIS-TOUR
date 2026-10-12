package ru.gulyay.app;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public class MainActivityRecoveryTest {
    @Test public void historyErrorKeepsLastConfirmedRouteState() {
        assertEquals(RouteLifecycleRecovery.HistoryRouteState.UNCONFIRMED,
                RouteLifecycleRecovery.fromHistory(false, false, null));
        assertFalse(RouteLifecycleRecovery.shouldReplaceHistoryCards(false, 3, 3));
    }

    @Test public void successfulEmptyHistoryMeansRouteWasRemoved() {
        assertEquals(RouteLifecycleRecovery.HistoryRouteState.REMOVED,
                RouteLifecycleRecovery.fromHistory(true, false, null));
    }

    @Test public void routeWithoutWalkRestoresAsReady() {
        assertEquals(RouteLifecycleRecovery.HistoryRouteState.READY,
                RouteLifecycleRecovery.fromHistory(true, true, null));
    }

    @Test public void stoppedAndCompletedRoutesNeverRestoreAsReady() {
        assertEquals(RouteLifecycleRecovery.HistoryRouteState.TERMINAL,
                RouteLifecycleRecovery.fromHistory(true, true, "STOPPED"));
        assertEquals(RouteLifecycleRecovery.HistoryRouteState.TERMINAL,
                RouteLifecycleRecovery.fromHistory(true, true, "COMPLETED"));
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
}
