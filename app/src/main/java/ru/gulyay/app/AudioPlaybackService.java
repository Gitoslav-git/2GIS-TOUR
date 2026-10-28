package ru.gulyay.app;

import android.content.SharedPreferences;
import android.os.Handler;
import android.os.Looper;
import androidx.annotation.Nullable;
import androidx.media3.common.AudioAttributes;
import androidx.media3.common.C;
import androidx.media3.common.MediaItem;
import androidx.media3.common.Player;
import androidx.media3.exoplayer.ExoPlayer;
import androidx.media3.session.MediaSession;
import androidx.media3.session.MediaSessionService;

/** The single app-wide player. It deliberately lives outside MapActivity's :map process. */
public final class AudioPlaybackService extends MediaSessionService {
    private static final String PREFERENCES = "audio_playback_service";
    private static final String STORY_ID = "story_id";
    private static final String POSITION = "position";
    private static final String FINISHED = "finished";

    private final Handler handler = new Handler(Looper.getMainLooper());
    private ExoPlayer player;
    private MediaSession mediaSession;
    private final Runnable positionSaver = new Runnable() {
        @Override public void run() {
            persistPlayback();
            if (player != null && player.isPlaying()) handler.postDelayed(this, 1_000L);
        }
    };

    @Override public void onCreate() {
        super.onCreate();
        player = new ExoPlayer.Builder(this)
                .setSeekBackIncrementMs(15_000L)
                .setSeekForwardIncrementMs(15_000L)
                .setAudioAttributes(new AudioAttributes.Builder()
                        .setContentType(C.AUDIO_CONTENT_TYPE_SPEECH)
                        .setUsage(C.USAGE_MEDIA)
                        .build(), true)
                .build();
        player.addListener(new Player.Listener() {
            @Override public void onEvents(Player source, Player.Events events) {
                persistPlayback();
                handler.removeCallbacks(positionSaver);
                if (source.isPlaying()) handler.postDelayed(positionSaver, 1_000L);
            }
        });
        mediaSession = new MediaSession.Builder(this, player).build();
        restorePlaybackWithoutAutoplay();
    }

    @Nullable @Override public MediaSession onGetSession(
            MediaSession.ControllerInfo controllerInfo) {
        return mediaSession;
    }

    private void restorePlaybackWithoutAutoplay() {
        SharedPreferences preferences = getSharedPreferences(PREFERENCES, MODE_PRIVATE);
        AudioStoryCatalog.Story story = AudioStoryCatalog.forCatalogId(
                preferences.getString(STORY_ID, null));
        if (story == null) return;
        long position = Math.max(0L, preferences.getLong(POSITION, 0L));
        player.setMediaItem(AudioStoryCatalog.mediaItem(story));
        player.prepare();
        player.seekTo(position);
        player.pause();
    }

    private void persistPlayback() {
        if (player == null) return;
        MediaItem item = player.getCurrentMediaItem();
        SharedPreferences.Editor editor = getSharedPreferences(PREFERENCES, MODE_PRIVATE).edit();
        if (item == null) {
            editor.clear().apply();
            return;
        }
        long duration = player.getDuration();
        long position = Math.max(0L, player.getCurrentPosition());
        editor.putString(STORY_ID, item.mediaId)
                .putLong(POSITION, position)
                .putBoolean(FINISHED, player.getPlaybackState() == Player.STATE_ENDED
                        || (duration > 0L && position >= duration))
                .apply();
    }

    @Override public void onTaskRemoved(android.content.Intent rootIntent) {
        persistPlayback();
        super.onTaskRemoved(rootIntent);
    }

    @Override public void onDestroy() {
        handler.removeCallbacksAndMessages(null);
        persistPlayback();
        if (mediaSession != null) mediaSession.release();
        mediaSession = null;
        if (player != null) player.release();
        player = null;
        super.onDestroy();
    }
}
