package ru.gulyay.app;

import java.io.IOException;

/** Bounded retry decision for route reads before a saved offline snapshot is used. */
final class RouteLoadRetryPolicy {
    static final long RETRY_DELAY_MILLIS = 350L;
    private static final int MAX_RETRIES = 1;

    private RouteLoadRetryPolicy() { }

    interface Operation<T> {
        T run() throws Exception;
    }

    interface TransientResult<T> {
        boolean test(T result);
    }

    static <T> T execute(Operation<T> operation,
                         TransientResult<T> transientResult) throws Exception {
        for (int attempt = 0; ; attempt++) {
            try {
                T result = operation.run();
                if (!transientResult.test(result) || !shouldRetryHttp(attempt)) return result;
            } catch (Exception error) {
                if (!shouldRetry(error, attempt)) throw error;
            }
            Thread.sleep(RETRY_DELAY_MILLIS);
        }
    }

    static boolean shouldRetry(Throwable error, int completedAttempts) {
        return completedAttempts < MAX_RETRIES && error instanceof IOException;
    }

    static boolean shouldRetryHttp(int completedAttempts) {
        return completedAttempts < MAX_RETRIES;
    }
}
