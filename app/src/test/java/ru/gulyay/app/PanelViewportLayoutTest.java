package ru.gulyay.app;

import org.junit.Test;

import static org.junit.Assert.assertEquals;

public final class PanelViewportLayoutTest {
    @Test public void collapsedSheetKeepsFooterBelowVisibleViewport() {
        assertEquals(0, PanelViewportLayout.footerLift(1000, 200, 32));
    }

    @Test public void halfExpandedSheetPinsFooterAboveNavigationInset() {
        assertEquals(432, PanelViewportLayout.footerLift(1000, 600, 32));
    }

    @Test public void expandedSheetKeepsSmallTopOffsetAndNavigationInset() {
        assertEquals(52, PanelViewportLayout.footerLift(1000, 980, 32));
    }

    @Test public void invalidInsetsCannotPushFooterDown() {
        assertEquals(400, PanelViewportLayout.footerLift(1000, 600, -20));
    }
}
