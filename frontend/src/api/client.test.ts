import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiFetch, markAuthStateChanged, SessionExpiredError } from "./client";

function jsonResponse(body: unknown, init: ResponseInit) {
    return new Response(JSON.stringify(body), {
        ...init,
        headers: {
            "Content-Type": "application/json",
            ...(init.headers ?? {}),
        },
    });
}

describe("apiFetch auth refresh", () => {
    beforeEach(() => {
        vi.restoreAllMocks();
    });

    it("dispatches auth-expired when refresh fails for the current auth state", async () => {
        const listener = vi.fn();
        window.addEventListener("troop:auth-expired", listener);
        vi.stubGlobal(
            "fetch",
            vi.fn()
                .mockResolvedValueOnce(jsonResponse({ detail: "Invalid token" }, { status: 401 }))
                .mockResolvedValueOnce(jsonResponse({ detail: "Invalid refresh token" }, { status: 401 }))
        );

        await expect(apiFetch("/auth/me")).rejects.toBeInstanceOf(SessionExpiredError);

        expect(listener).toHaveBeenCalledOnce();
        window.removeEventListener("troop:auth-expired", listener);
    });

    it("does not expire a newer sign-in when an older refresh fails later", async () => {
        const listener = vi.fn();
        let resolveRefresh: (response: Response) => void = () => undefined;
        window.addEventListener("troop:auth-expired", listener);
        vi.stubGlobal(
            "fetch",
            vi.fn()
                .mockResolvedValueOnce(jsonResponse({ detail: "Invalid token" }, { status: 401 }))
                .mockReturnValueOnce(
                    new Promise<Response>((resolve) => {
                        resolveRefresh = resolve;
                    })
                )
        );

        const request = apiFetch("/auth/me").catch((error: unknown) => error);
        await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
        markAuthStateChanged();
        resolveRefresh(jsonResponse({ detail: "Invalid refresh token" }, { status: 401 }));

        await expect(request).resolves.toBeInstanceOf(SessionExpiredError);
        expect(listener).not.toHaveBeenCalled();
        window.removeEventListener("troop:auth-expired", listener);
    });
});
