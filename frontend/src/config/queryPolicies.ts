import type { UseQueryOptions } from "@tanstack/react-query";

export const queryPolicies = {
    reference: {
        staleTime: 15 * 60_000,
        gcTime: 60 * 60_000,
        refetchOnWindowFocus: false,
    },
    userScoped: {
        staleTime: 60_000,
        gcTime: 15 * 60_000,
        refetchOnWindowFocus: false,
    },
    operational: {
        staleTime: 30_000,
        gcTime: 5 * 60_000,
        refetchOnWindowFocus: true,
    },
    realtime: {
        staleTime: 0,
        gcTime: 2 * 60_000,
        refetchOnWindowFocus: true,
    },
} as const;

export type QueryPolicy = Partial<Pick<UseQueryOptions<unknown>, "staleTime" | "gcTime" | "refetchOnWindowFocus">>;
