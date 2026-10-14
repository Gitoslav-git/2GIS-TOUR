package ru.gulyay.app;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public class RouteStartLocationTest {
    @Test public void acceptsFreshAccurateMeasurement() {
        assertTrue(new RouteStartLocation(55.75, 37.61, 25.0, 100_000L)
                .isFreshAndAccurate(159_999L));
    }

    @Test public void rejectsMeasurementOlderThanMinute() {
        assertFalse(new RouteStartLocation(55.75, 37.61, 25.0, 100_000L)
                .isFreshAndAccurate(160_001L));
    }

    @Test public void rejectsInaccurateMeasurement() {
        assertFalse(new RouteStartLocation(55.75, 37.61, 100.1, 100_000L)
                .isFreshAndAccurate(100_100L));
    }

    @Test public void rejectsFutureAndRestoredMeasurementWithoutTimestamp() {
        assertFalse(new RouteStartLocation(55.75, 37.61, 10.0, 101_000L)
                .isFreshAndAccurate(100_000L));
        assertFalse(new RouteStartLocation(55.75, 37.61, 10.0, 0L)
                .isFreshAndAccurate(100_000L));
    }

    @Test public void rejectsInvalidCoordinates() {
        assertFalse(new RouteStartLocation(91.0, 37.61, 10.0, 100_000L)
                .isFreshAndAccurate(100_100L));
    }
}
