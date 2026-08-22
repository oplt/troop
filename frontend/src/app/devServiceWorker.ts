/**
 * Production installs a PWA service worker. If the same localhost origin was
 * previously used for a production preview, that worker can keep serving an
 * old app shell while Vite serves new lazy route modules. Remove it before the
 * development app mounts so route imports always come from the current source.
 */
export async function clearDevServiceWorkers(): Promise<boolean> {
    if (!import.meta.env.DEV || !("serviceWorker" in navigator)) {
        return false;
    }

    try {
        const registrations = await navigator.serviceWorker.getRegistrations();
        if (registrations.length === 0) {
            return false;
        }

        const results = await Promise.all(
            registrations.map((registration) => registration.unregister()),
        );
        return results.some(Boolean) && navigator.serviceWorker.controller !== null;
    } catch {
        // Service worker cleanup must never prevent the development app mounting.
        return false;
    }
}
