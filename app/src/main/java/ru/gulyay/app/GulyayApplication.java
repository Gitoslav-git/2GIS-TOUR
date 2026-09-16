package ru.gulyay.app;

import android.app.Application;
import java.io.IOException;
import java.io.InputStream;
import ru.dgis.sdk.Context;
import ru.dgis.sdk.DGis;
import ru.dgis.sdk.PersonalDataCollectionConsent;
import ru.dgis.sdk.map.GlobalMapOptions;
import ru.dgis.sdk.map.GraphicsApi;
import ru.dgis.sdk.platform.HttpOptions;
import ru.dgis.sdk.platform.KeyFromAsset;
import ru.dgis.sdk.platform.KeySource;
import ru.dgis.sdk.platform.LogOptions;
import ru.dgis.sdk.platform.StorageOptions;
import ru.dgis.sdk.platform.VendorConfig;

public final class GulyayApplication extends Application {
    private Context sdkContext;
    private String mapError;

    @Override public void onCreate() {
        super.onCreate();
        if (!hasMapKey()) {
            mapError = "В APK не добавлен мобильный ключ 2ГИС dgissdk.key. " +
                    "Добавьте GitHub Actions secret DGIS_SDK_KEY_BASE64 и пересоберите APK.";
            return;
        }
        try {
            // OpenGL is selected deliberately for predictable Android Emulator support.
            sdkContext = DGis.initialize(
                    this,
                    new HttpOptions(),
                    new LogOptions(),
                    new VendorConfig(),
                    new KeySource(new KeyFromAsset("dgissdk.key")),
                    PersonalDataCollectionConsent.DENIED,
                    null,
                    null,
                    new GlobalMapOptions(GraphicsApi.OPEN_GL, false),
                    new StorageOptions()
            );
        } catch (RuntimeException error) {
            mapError = "Не удалось запустить карту 2ГИС. Проверьте мобильный ключ и его подписку.";
        }
    }

    Context sdkContext() {
        return sdkContext;
    }

    String mapError() {
        return mapError;
    }

    private boolean hasMapKey() {
        try (InputStream ignored = getAssets().open("dgissdk.key")) {
            return true;
        } catch (IOException error) {
            return false;
        }
    }
}
