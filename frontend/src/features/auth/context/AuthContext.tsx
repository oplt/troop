import {
    type PropsWithChildren,
    useEffect,
} from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { logout as logoutRequest, me, type AuthUser } from "../../../api/auth";
import { markAuthStateChanged, onAuthExpired } from "../../../api/client";
import { AuthContext } from "./authContext";

export function AuthProvider({ children }: PropsWithChildren) {
    const queryClient = useQueryClient();
    const {
        data: currentUser = null,
        isPending,
        isError,
    } = useQuery<AuthUser | null>({
        queryKey: ["auth", "me"],
        queryFn: me,
        retry: false,
        staleTime: 0,
        gcTime: 0,
        refetchOnMount: "always",
    });

    const isAuthenticated = currentUser !== null;
    const isReady = !isPending || isError;

    useEffect(() => {
        return onAuthExpired(() => {
            queryClient.setQueryData(["auth", "me"], null);
            void queryClient.cancelQueries();
            queryClient.removeQueries({
                predicate: (query) => query.queryKey[0] !== "auth",
            });
        });
    }, [queryClient]);

    async function logout() {
        markAuthStateChanged();
        await logoutRequest().catch(() => undefined);
        queryClient.setQueryData(["auth", "me"], null);
        queryClient.removeQueries({
            predicate: (query) => query.queryKey[0] !== "auth",
        });
    }

    function setAuthenticated(user: AuthUser) {
        markAuthStateChanged();
        queryClient.setQueryData(["auth", "me"], user);
    }

    return (
        <AuthContext.Provider
            value={{
                isReady,
                isAuthenticated,
                isAdmin: currentUser?.is_admin ?? false,
                isMfaEnabled: currentUser?.mfa_enabled ?? false,
                currentUser,
                logout,
                setAuthenticated,
            }}
        >
            {children}
        </AuthContext.Provider>
    );
}
