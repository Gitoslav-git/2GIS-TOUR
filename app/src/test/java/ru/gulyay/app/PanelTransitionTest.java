package ru.gulyay.app;

import org.junit.Test;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

public final class PanelTransitionTest {
    @Test public void movingToVisitingForSamePointOpensPanel() {
        assertTrue(PanelTransition.isNewArrival(
                "route_v1", "route_v1", "MOVING", 2, "VISITING", 2));
    }

    @Test public void repeatedVisitingDoesNotOpenPanel() {
        assertFalse(PanelTransition.isNewArrival(
                "route_v1", "route_v1", "VISITING", 2, "VISITING", 2));
    }

    @Test public void restoredVisitingDoesNotOpenPanel() {
        assertFalse(PanelTransition.isNewArrival(
                null, "route_v1", null, 0, "VISITING", 2));
    }

    @Test public void differentRouteDoesNotReuseArrival() {
        assertFalse(PanelTransition.isNewArrival(
                "route_a_v1", "route_b_v1", "MOVING", 2, "VISITING", 2));
    }
}
