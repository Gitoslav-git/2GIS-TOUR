package ru.gulyay.app;

/** Pure lifecycle checks that keep optional commercial responses fail-closed. */
final class PartnerOfferRequestPolicy {
    private PartnerOfferRequestPolicy() { }

    static boolean eligible(String status, String phase, int pointOrder) {
        return "ACTIVE".equals(status) && "VISITING".equals(phase) && pointOrder > 0;
    }

    static String key(String walkId, int pointOrder) {
        return walkId == null ? "" : walkId + ":" + pointOrder;
    }

    static boolean isCurrent(String expectedKey, int expectedGeneration,
                             String walkId, String status, String phase,
                             int pointOrder, int currentGeneration) {
        return expectedGeneration == currentGeneration
                && eligible(status, phase, pointOrder)
                && expectedKey != null
                && expectedKey.equals(key(walkId, pointOrder));
    }
}
