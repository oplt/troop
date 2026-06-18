import { useQuery } from "@tanstack/react-query";
import { getProfile, type Profile } from "../api/profile";
import { defaultQueryStaleTimeMs, queryKeys } from "../config/queryKeys";
import { useAuth } from "./useAuth";

/** Auth session user + optional profile extension (avatar, bio). Avoids duplicate `/users/me`. */
export function useCanonicalUser(options?: { profileEnabled?: boolean }) {
    const { currentUser, isAuthenticated, isReady } = useAuth();
    const authReady = isReady && isAuthenticated;
    const profileEnabled = options?.profileEnabled ?? authReady;

    const { data: profile } = useQuery<Profile>({
        queryKey: queryKeys.profile.root,
        queryFn: getProfile,
        staleTime: defaultQueryStaleTimeMs,
        enabled: profileEnabled,
    });

    return {
        user: currentUser,
        profile,
        authReady,
    };
}
