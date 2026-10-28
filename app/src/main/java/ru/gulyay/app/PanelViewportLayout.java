package ru.gulyay.app;

/** Pure layout math for controls pinned to the visible part of a full-height sheet. */
final class PanelViewportLayout {
    private static final float MIN_PINNED_VISIBLE_RATIO = 0.45f;

    private PanelViewportLayout() { }

    static int footerLift(int parentHeight, int visibleSheetHeight, int bottomInset) {
        if (parentHeight <= 0 || visibleSheetHeight <= 0
                || visibleSheetHeight < Math.round(parentHeight * MIN_PINNED_VISIBLE_RATIO)) {
            return 0;
        }
        int hiddenOverflow = Math.max(0, parentHeight - visibleSheetHeight);
        return hiddenOverflow + Math.max(0, bottomInset);
    }
}
