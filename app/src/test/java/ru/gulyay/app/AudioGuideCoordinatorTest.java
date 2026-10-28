package ru.gulyay.app;

import org.junit.Test;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

public final class AudioGuideCoordinatorTest {
    private static final long NOW = 1_000_000L;

    private static AudioGuideCoordinator available() {
        AudioGuideCoordinator state = new AudioGuideCoordinator();
        state.onVisit("walk:1", "msk002", NOW);
        return state;
    }

    @Test public void initialStateIsHidden() {
        assertEquals(AudioGuideCoordinator.UiState.HIDDEN,
                new AudioGuideCoordinator().uiState());
    }

    @Test public void catalogPrefixFindsBasilStory() {
        assertEquals("msk002", AudioStoryCatalog.forStablePlaceId("catalog:msk002").catalogId);
    }

    @Test public void providerIdFindsBasilStory() {
        assertEquals("msk002", AudioStoryCatalog.forStablePlaceId("4504127908471722").catalogId);
    }

    @Test public void catalogPrefixFindsGumMappedStory() {
        assertEquals("msk004", AudioStoryCatalog.forStablePlaceId("catalog:msk004").catalogId);
    }

    @Test public void providerIdFindsGumMappedStory() {
        assertEquals("msk004", AudioStoryCatalog.forStablePlaceId("4504127908391014").catalogId);
    }

    @Test public void rawCatalogIdIsAcceptedAsStableIdentity() {
        assertEquals("msk002", AudioStoryCatalog.forStablePlaceId("msk002").catalogId);
    }

    @Test public void unknownPlaceHasNoStory() {
        assertNull(AudioStoryCatalog.forStablePlaceId("some-other-place"));
    }

    @Test public void namesAreNotUsedAsIdentity() {
        assertNull(AudioStoryCatalog.forStablePlaceId("Храм Василия Блаженного"));
    }

    @Test public void firstArrivalMakesStoryAvailable() {
        assertEquals(AudioGuideCoordinator.UiState.AVAILABLE, available().uiState());
    }

    @Test public void sameArrivalRemainsAvailable() {
        AudioGuideCoordinator state = available();
        state.onVisit("walk:1", "msk002", NOW + 1);
        assertEquals(AudioGuideCoordinator.UiState.AVAILABLE, state.uiState());
    }

    @Test public void playingStateIsVisible() {
        AudioGuideCoordinator state = available();
        state.onPlayback("msk002", AudioGuideCoordinator.PlaybackState.PLAYING);
        assertEquals(AudioGuideCoordinator.UiState.PLAYING, state.uiState());
    }

    @Test public void pausedStateIsVisible() {
        AudioGuideCoordinator state = available();
        state.onPlayback("msk002", AudioGuideCoordinator.PlaybackState.PAUSED);
        assertEquals(AudioGuideCoordinator.UiState.PAUSED, state.uiState());
    }

    @Test public void finishedStateIsVisibleForReplay() {
        AudioGuideCoordinator state = available();
        state.onPlayback("msk002", AudioGuideCoordinator.PlaybackState.FINISHED);
        assertEquals(AudioGuideCoordinator.UiState.FINISHED, state.uiState());
    }

    @Test public void playbackErrorReturnsRetryableAvailableUi() {
        AudioGuideCoordinator state = available();
        state.onPlayback("msk002", AudioGuideCoordinator.PlaybackState.ERROR);
        assertEquals(AudioGuideCoordinator.UiState.AVAILABLE, state.uiState());
    }

    @Test public void closeHidesAndResetsCurrentStory() {
        AudioGuideCoordinator state = available();
        state.closeCurrentVisit();
        assertEquals(AudioGuideCoordinator.UiState.HIDDEN, state.uiState());
        assertNull(state.currentStoryId());
    }

    @Test public void closeDismissesSameVisit() {
        AudioGuideCoordinator state = available();
        state.closeCurrentVisit();
        state.onVisit("walk:1", "msk002", NOW + 1);
        assertEquals(AudioGuideCoordinator.UiState.HIDDEN, state.uiState());
    }

    @Test public void laterVisitCanOfferDismissedStoryAgain() {
        AudioGuideCoordinator state = available();
        state.closeCurrentVisit();
        state.onVisit("walk:2", "msk002", NOW + 1);
        assertEquals(AudioGuideCoordinator.UiState.AVAILABLE, state.uiState());
    }

    @Test public void secondStoryCreatesNewAvailableState() {
        AudioGuideCoordinator state = available();
        state.onPlayback("msk002", AudioGuideCoordinator.PlaybackState.PLAYING);
        state.onVisit("walk:2", "msk004", NOW + 1);
        assertEquals(AudioGuideCoordinator.UiState.NEW_AVAILABLE, state.uiState());
        assertEquals("msk002", state.currentStoryId());
        assertEquals("msk004", state.pendingStoryId());
    }

    @Test public void repeatedSecondStoryKeepsSinglePendingStory() {
        AudioGuideCoordinator state = available();
        state.onVisit("walk:2", "msk004", NOW + 1);
        state.onVisit("walk:2", "msk004", NOW + 2);
        assertEquals("msk004", state.pendingStoryId());
    }

    @Test public void switchingReturnsPendingStory() {
        AudioGuideCoordinator state = available();
        state.onVisit("walk:2", "msk004", NOW + 1);
        assertEquals("msk004", state.switchToPending(NOW + 2));
    }

    @Test public void switchingStopsShowingPendingMarker() {
        AudioGuideCoordinator state = available();
        state.onVisit("walk:2", "msk004", NOW + 1);
        state.switchToPending(NOW + 2);
        assertNull(state.pendingStoryId());
        assertEquals(AudioGuideCoordinator.UiState.PLAYING, state.uiState());
    }

    @Test public void switchingWithoutPendingDoesNothing() {
        AudioGuideCoordinator state = available();
        assertNull(state.switchToPending(NOW));
        assertEquals("msk002", state.currentStoryId());
    }

    @Test public void returningToCurrentStoryClearsPendingMarker() {
        AudioGuideCoordinator state = available();
        state.onVisit("walk:2", "msk004", NOW + 1);
        state.onVisit("walk:3", "msk002", NOW + 2);
        assertNull(state.pendingStoryId());
        assertEquals(AudioGuideCoordinator.UiState.AVAILABLE, state.uiState());
    }

    @Test public void confirmedExitDoesNotHideImmediately() {
        AudioGuideCoordinator state = available();
        state.onConfirmedExit("walk:1", NOW + 1);
        assertEquals(AudioGuideCoordinator.UiState.AVAILABLE, state.uiState());
    }

    @Test public void wrongVisitCannotStartExitTimeout() {
        AudioGuideCoordinator state = available();
        state.onConfirmedExit("walk:other", NOW);
        assertFalse(state.expireIfNeeded(NOW + AudioGuideCoordinator.EXIT_INACTIVITY_MILLIS));
    }

    @Test public void nonPlayingStoryDoesNotExpireBeforeFiveMinutes() {
        AudioGuideCoordinator state = available();
        state.onConfirmedExit("walk:1", NOW);
        assertFalse(state.expireIfNeeded(
                NOW + AudioGuideCoordinator.EXIT_INACTIVITY_MILLIS - 1));
    }

    @Test public void nonPlayingStoryExpiresAtFiveMinutes() {
        AudioGuideCoordinator state = available();
        state.onConfirmedExit("walk:1", NOW);
        assertTrue(state.expireIfNeeded(NOW + AudioGuideCoordinator.EXIT_INACTIVITY_MILLIS));
        assertEquals(AudioGuideCoordinator.UiState.HIDDEN, state.uiState());
    }

    @Test public void interactionResetsExitInactivityClock() {
        AudioGuideCoordinator state = available();
        state.onConfirmedExit("walk:1", NOW);
        state.onUserInteraction(NOW + AudioGuideCoordinator.EXIT_INACTIVITY_MILLIS - 1);
        assertFalse(state.expireIfNeeded(
                NOW + AudioGuideCoordinator.EXIT_INACTIVITY_MILLIS + 1));
    }

    @Test public void playingStoryIsExemptFromExitTimeout() {
        AudioGuideCoordinator state = available();
        state.onPlayback("msk002", AudioGuideCoordinator.PlaybackState.PLAYING);
        state.onConfirmedExit("walk:1", NOW);
        assertFalse(state.expireIfNeeded(
                NOW + 10 * AudioGuideCoordinator.EXIT_INACTIVITY_MILLIS));
    }

    @Test public void pausedStoryCanExpireAfterExit() {
        AudioGuideCoordinator state = available();
        state.onPlayback("msk002", AudioGuideCoordinator.PlaybackState.PLAYING);
        state.onConfirmedExit("walk:1", NOW);
        state.onPlayback("msk002", AudioGuideCoordinator.PlaybackState.PAUSED);
        assertTrue(state.expireIfNeeded(NOW + AudioGuideCoordinator.EXIT_INACTIVITY_MILLIS));
    }

    @Test public void currentAudioLocationNeverTimesOut() {
        AudioGuideCoordinator state = available();
        assertFalse(state.expireIfNeeded(
                NOW + 10 * AudioGuideCoordinator.EXIT_INACTIVITY_MILLIS));
    }

    @Test public void unrelatedVisitDoesNotSuppressOldStoryTimeout() {
        AudioGuideCoordinator state = available();
        state.onConfirmedExit("walk:1", NOW);
        state.onVisit("walk:other", null, NOW + 1);
        assertTrue(state.expireIfNeeded(NOW + AudioGuideCoordinator.EXIT_INACTIVITY_MILLIS));
    }

    @Test public void pendingStoryDoesNotReplacePlayingStoryAutomatically() {
        AudioGuideCoordinator state = available();
        state.onPlayback("msk002", AudioGuideCoordinator.PlaybackState.PLAYING);
        state.onVisit("walk:2", "msk004", NOW + 1);
        assertEquals("msk002", state.currentStoryId());
        assertEquals(AudioGuideCoordinator.PlaybackState.PLAYING, state.playbackState());
    }

    @Test public void closeAlsoClearsPendingStory() {
        AudioGuideCoordinator state = available();
        state.onVisit("walk:2", "msk004", NOW + 1);
        state.closeCurrentVisit();
        assertNull(state.pendingStoryId());
    }

    @Test public void snapshotRoundTripPreservesPendingStory() {
        AudioGuideCoordinator source = available();
        source.onPlayback("msk002", AudioGuideCoordinator.PlaybackState.PAUSED);
        source.onVisit("walk:2", "msk004", NOW + 1);
        AudioGuideCoordinator restored = new AudioGuideCoordinator();
        restored.restore(source.snapshot());
        assertEquals(AudioGuideCoordinator.UiState.NEW_AVAILABLE, restored.uiState());
        assertEquals("msk004", restored.pendingStoryId());
    }

    @Test public void restoredPlayingSnapshotRemainsVisible() {
        AudioGuideCoordinator source = available();
        source.onPlayback("msk002", AudioGuideCoordinator.PlaybackState.PLAYING);
        AudioGuideCoordinator restored = new AudioGuideCoordinator();
        restored.restore(source.snapshot());
        assertEquals(AudioGuideCoordinator.UiState.PLAYING, restored.uiState());
    }

    @Test public void restoredHiddenSnapshotRemainsHidden() {
        AudioGuideCoordinator source = available();
        source.closeCurrentVisit();
        AudioGuideCoordinator restored = new AudioGuideCoordinator();
        restored.restore(source.snapshot());
        assertEquals(AudioGuideCoordinator.UiState.HIDDEN, restored.uiState());
    }

    @Test public void playbackEventCanRestoreSelectedStoryIdentity() {
        AudioGuideCoordinator state = new AudioGuideCoordinator();
        state.restore(new AudioGuideCoordinator.Snapshot(null, null, null, null,
                null, null, null, -1L, 0L,
                AudioGuideCoordinator.PlaybackState.IDLE, false));
        state.onPlayback("msk004", AudioGuideCoordinator.PlaybackState.PAUSED);
        assertEquals("msk004", state.currentStoryId());
        assertEquals(AudioGuideCoordinator.UiState.PAUSED, state.uiState());
    }

    @Test public void userInteractionDoesNotChangePlaybackState() {
        AudioGuideCoordinator state = available();
        state.onPlayback("msk002", AudioGuideCoordinator.PlaybackState.PAUSED);
        state.onUserInteraction(NOW + 10);
        assertEquals(AudioGuideCoordinator.PlaybackState.PAUSED, state.playbackState());
    }

    @Test public void gumUsesRequestedMonumentTitle() {
        assertEquals("Памятник Минину и Пожарскому",
                AudioStoryCatalog.forCatalogId("msk004").title);
    }

    @Test public void basilUsesRequestedTitle() {
        assertEquals("Храм Василия Блаженного",
                AudioStoryCatalog.forCatalogId("msk002").title);
    }

    @Test public void closeAfterExitStillDismissesOriginatingVisit() {
        AudioGuideCoordinator state = available();
        state.onConfirmedExit("walk:1", NOW);
        state.closeCurrentVisit();
        state.onVisit("walk:1", "msk002", NOW + 1);
        assertEquals(AudioGuideCoordinator.UiState.HIDDEN, state.uiState());
    }
}
