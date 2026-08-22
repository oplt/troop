import { afterEach, describe, expect, it, vi } from "vitest";
import { clearDevServiceWorkers } from "./devServiceWorker";

const originalServiceWorker = Object.getOwnPropertyDescriptor(navigator, "serviceWorker");

function setServiceWorker(value: unknown) {
    Object.defineProperty(navigator, "serviceWorker", {
        configurable: true,
        value,
    });
}

afterEach(() => {
    if (originalServiceWorker) {
        Object.defineProperty(navigator, "serviceWorker", originalServiceWorker);
    } else {
        delete (navigator as { serviceWorker?: unknown }).serviceWorker;
    }
});

describe("clearDevServiceWorkers", () => {
    it("unregisters stale localhost workers and requests one clean reload", async () => {
        const unregister = vi.fn().mockResolvedValue(true);
        setServiceWorker({
            controller: {},
            getRegistrations: vi.fn().mockResolvedValue([{ unregister }]),
        });

        await expect(clearDevServiceWorkers()).resolves.toBe(true);
        expect(unregister).toHaveBeenCalledOnce();
    });

    it("fails open when the browser refuses service-worker access", async () => {
        setServiceWorker({
            controller: {},
            getRegistrations: vi.fn().mockRejectedValue(new Error("denied")),
        });

        await expect(clearDevServiceWorkers()).resolves.toBe(false);
    });

    it("does not request a reload when unregistering fails", async () => {
        const unregister = vi.fn().mockResolvedValue(false);
        setServiceWorker({
            controller: {},
            getRegistrations: vi.fn().mockResolvedValue([{ unregister }]),
        });

        await expect(clearDevServiceWorkers()).resolves.toBe(false);
        expect(unregister).toHaveBeenCalledOnce();
    });
});
