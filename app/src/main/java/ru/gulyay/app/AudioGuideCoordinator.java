package ru.gulyay.app;

import java.util.Objects;

/** Pure audio-guide state machine. Android playback and views are adapters around it. */
final class AudioGuideCoordinator {
    static final long EXIT_INACTIVITY_MILLIS = 5 * 60 * 1_000L;

    enum PlaybackState { IDLE, PLAYING, PAUSED, FINISHED, ERROR }
    enum UiState { HIDDEN, AVAILABLE, PLAYING, PAUSED, FINISHED, NEW_AVAILABLE }

    static final class Snapshot {
        final String currentStoryId;
        final String pendingStoryId;
        final String currentStoryVisitKey;
        final String pendingStoryVisitKey;
        final String activeVisitKey;
        final String activeVisitStoryId;
        final String dismissedVisitKey;
        final long confirmedExitAtMillis;
        final long lastInteractionAtMillis;
        final PlaybackState playbackState;
        final boolean hidden;

        Snapshot(String currentStoryId, String pendingStoryId,
                 String currentStoryVisitKey, String pendingStoryVisitKey,
                 String activeVisitKey, String activeVisitStoryId, String dismissedVisitKey,
                 long confirmedExitAtMillis, long lastInteractionAtMillis,
                 PlaybackState playbackState, boolean hidden) {
            this.currentStoryId = currentStoryId;
            this.pendingStoryId = pendingStoryId;
            this.currentStoryVisitKey = currentStoryVisitKey;
            this.pendingStoryVisitKey = pendingStoryVisitKey;
            this.activeVisitKey = activeVisitKey;
            this.activeVisitStoryId = activeVisitStoryId;
            this.dismissedVisitKey = dismissedVisitKey;
            this.confirmedExitAtMillis = confirmedExitAtMillis;
            this.lastInteractionAtMillis = lastInteractionAtMillis;
            this.playbackState = playbackState == null ? PlaybackState.IDLE : playbackState;
            this.hidden = hidden;
        }
    }

    private String currentStoryId;
    private String pendingStoryId;
    private String currentStoryVisitKey;
    private String pendingStoryVisitKey;
    private String activeVisitKey;
    private String activeVisitStoryId;
    private String dismissedVisitKey;
    private long confirmedExitAtMillis = -1L;
    private long lastInteractionAtMillis;
    private PlaybackState playbackState = PlaybackState.IDLE;
    private boolean hidden = true;

    void restore(Snapshot snapshot) {
        if (snapshot == null) return;
        currentStoryId = snapshot.currentStoryId;
        pendingStoryId = snapshot.pendingStoryId;
        currentStoryVisitKey = snapshot.currentStoryVisitKey;
        pendingStoryVisitKey = snapshot.pendingStoryVisitKey;
        activeVisitKey = snapshot.activeVisitKey;
        activeVisitStoryId = snapshot.activeVisitStoryId;
        dismissedVisitKey = snapshot.dismissedVisitKey;
        confirmedExitAtMillis = snapshot.confirmedExitAtMillis;
        lastInteractionAtMillis = snapshot.lastInteractionAtMillis;
        playbackState = snapshot.playbackState;
        hidden = snapshot.hidden;
    }

    Snapshot snapshot() {
        return new Snapshot(currentStoryId, pendingStoryId,
                currentStoryVisitKey, pendingStoryVisitKey, activeVisitKey,
                activeVisitStoryId, dismissedVisitKey, confirmedExitAtMillis,
                lastInteractionAtMillis, playbackState, hidden);
    }

    void onVisit(String visitKey, String storyId, long nowMillis) {
        activeVisitKey = visitKey;
        activeVisitStoryId = storyId;
        if (storyId == null || Objects.equals(visitKey, dismissedVisitKey)) return;
        hidden = false;
        if (currentStoryId == null) {
            currentStoryId = storyId;
            pendingStoryId = null;
            currentStoryVisitKey = visitKey;
            pendingStoryVisitKey = null;
            playbackState = PlaybackState.IDLE;
            lastInteractionAtMillis = nowMillis;
            confirmedExitAtMillis = -1L;
        } else if (!Objects.equals(currentStoryId, storyId)) {
            pendingStoryId = storyId;
            pendingStoryVisitKey = visitKey;
        } else {
            pendingStoryId = null;
            pendingStoryVisitKey = null;
            currentStoryVisitKey = visitKey;
            confirmedExitAtMillis = -1L;
        }
    }

    void onConfirmedExit(String visitKey, long nowMillis) {
        if (visitKey == null || !Objects.equals(activeVisitKey, visitKey)) return;
        activeVisitKey = null;
        activeVisitStoryId = null;
        confirmedExitAtMillis = nowMillis;
    }

    void onPlayback(String storyId, PlaybackState state) {
        if (storyId != null) currentStoryId = storyId;
        playbackState = state == null ? PlaybackState.IDLE : state;
        if (playbackState == PlaybackState.PLAYING) hidden = false;
    }

    void onUserInteraction(long nowMillis) {
        lastInteractionAtMillis = nowMillis;
    }

    void closeCurrentVisit() {
        if (activeVisitKey != null) dismissedVisitKey = activeVisitKey;
        else if (currentStoryVisitKey != null) dismissedVisitKey = currentStoryVisitKey;
        currentStoryId = null;
        pendingStoryId = null;
        currentStoryVisitKey = null;
        pendingStoryVisitKey = null;
        playbackState = PlaybackState.IDLE;
        hidden = true;
        confirmedExitAtMillis = -1L;
    }

    String switchToPending(long nowMillis) {
        if (pendingStoryId == null) return null;
        currentStoryId = pendingStoryId;
        currentStoryVisitKey = pendingStoryVisitKey;
        pendingStoryId = null;
        pendingStoryVisitKey = null;
        playbackState = PlaybackState.PLAYING;
        hidden = false;
        lastInteractionAtMillis = nowMillis;
        return currentStoryId;
    }

    boolean expireIfNeeded(long nowMillis) {
        boolean stillAtCurrentStory = activeVisitKey != null
                && Objects.equals(activeVisitStoryId, currentStoryId);
        if (hidden || currentStoryId == null || stillAtCurrentStory
                || confirmedExitAtMillis < 0L || playbackState == PlaybackState.PLAYING) {
            return false;
        }
        long inactivityStart = Math.max(confirmedExitAtMillis, lastInteractionAtMillis);
        if (nowMillis - inactivityStart < EXIT_INACTIVITY_MILLIS) return false;
        currentStoryId = null;
        pendingStoryId = null;
        currentStoryVisitKey = null;
        pendingStoryVisitKey = null;
        playbackState = PlaybackState.IDLE;
        hidden = true;
        return true;
    }

    UiState uiState() {
        if (hidden || currentStoryId == null) return UiState.HIDDEN;
        if (pendingStoryId != null) return UiState.NEW_AVAILABLE;
        switch (playbackState) {
            case PLAYING: return UiState.PLAYING;
            case PAUSED: return UiState.PAUSED;
            case FINISHED: return UiState.FINISHED;
            case ERROR:
            case IDLE:
            default: return UiState.AVAILABLE;
        }
    }

    String currentStoryId() { return currentStoryId; }
    String pendingStoryId() { return pendingStoryId; }
    String activeVisitKey() { return activeVisitKey; }
    PlaybackState playbackState() { return playbackState; }
}
