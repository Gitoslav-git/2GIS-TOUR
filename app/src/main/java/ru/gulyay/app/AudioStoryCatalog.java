package ru.gulyay.app;

import android.content.Context;
import android.content.res.AssetFileDescriptor;
import android.media.MediaMetadataRetriever;
import androidx.media3.common.MediaItem;
import androidx.media3.common.MediaMetadata;
import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Local-only audio stories keyed by stable catalog/place entity identities. */
final class AudioStoryCatalog {
    static final class Story {
        final String catalogId;
        final String title;
        final String assetPath;
        final List<String> stablePlaceIds;

        Story(String catalogId, String title, String assetPath, String... stablePlaceIds) {
            this.catalogId = catalogId;
            this.title = title;
            this.assetPath = assetPath;
            this.stablePlaceIds = Collections.unmodifiableList(Arrays.asList(stablePlaceIds));
        }
    }

    static final class AvailableStory {
        final Story story;
        final long durationMillis;

        AvailableStory(Story story, long durationMillis) {
            this.story = story;
            this.durationMillis = durationMillis;
        }
    }

    private static final Story BASIL_CATHEDRAL = new Story(
            "msk002",
            "Храм Василия Блаженного",
            "audio/03_krasnaya_ploshadj_hram_vasiliya_blazhennogo.mp3",
            "catalog:msk002", "4504127908471722");
    private static final Story MININ_POZHARSKY = new Story(
            "msk004",
            "Памятник Минину и Пожарскому",
            "audio/07_krasnaya_ploshadj_pamyatnik_mininu_i_pozharskomu.mp3",
            "catalog:msk004", "4504127908391014");
    private static final List<Story> STORIES = Collections.unmodifiableList(
            Arrays.asList(BASIL_CATHEDRAL, MININ_POZHARSKY));
    private static final Map<String, Story> BY_CATALOG_ID = byCatalogId();

    private AudioStoryCatalog() { }

    static Story forStablePlaceId(String placeId) {
        if (placeId == null) return null;
        for (Story story : STORIES) {
            if (story.catalogId.equals(placeId) || story.stablePlaceIds.contains(placeId)) {
                return story;
            }
        }
        return null;
    }

    static Story forCatalogId(String catalogId) {
        return catalogId == null ? null : BY_CATALOG_ID.get(catalogId);
    }

    static AvailableStory inspect(Context context, Story story) {
        if (context == null || story == null) return null;
        MediaMetadataRetriever retriever = new MediaMetadataRetriever();
        try (AssetFileDescriptor descriptor = context.getAssets().openFd(story.assetPath)) {
            retriever.setDataSource(descriptor.getFileDescriptor(), descriptor.getStartOffset(),
                    descriptor.getLength());
            String rawDuration = retriever.extractMetadata(
                    MediaMetadataRetriever.METADATA_KEY_DURATION);
            long duration = rawDuration == null ? 0L : Long.parseLong(rawDuration);
            return duration > 0L ? new AvailableStory(story, duration) : null;
        } catch (Exception ignored) {
            return null;
        } finally {
            try { retriever.release(); } catch (Exception ignored) { }
        }
    }

    static MediaItem mediaItem(Story story) {
        return new MediaItem.Builder()
                .setMediaId(story.catalogId)
                .setUri("asset:///" + story.assetPath)
                .setMediaMetadata(new MediaMetadata.Builder()
                        .setTitle(story.title)
                        .setArtist("Гуляй")
                        .setIsPlayable(true)
                        .build())
                .build();
    }

    private static Map<String, Story> byCatalogId() {
        Map<String, Story> result = new LinkedHashMap<>();
        for (Story story : STORIES) result.put(story.catalogId, story);
        return Collections.unmodifiableMap(result);
    }
}
