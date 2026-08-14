import { useCallback, useMemo, useState } from "react";

import type { NavPersona } from "./navConfig";
import {
    deriveNavPersona,
    NAV_PERSONA_STORAGE_KEY,
    readNavPersonaPreference,
    resolveNavPersona,
    writeNavPersonaPreference,
    type NavPersonaContext,
} from "./navPersona";

export function useNavPersona(ctx: NavPersonaContext) {
    const derived = useMemo(() => deriveNavPersona(ctx), [ctx.isAdmin, ctx.workspaceRole]);
    const [preference, setPreference] = useState<NavPersona | null>(() => readNavPersonaPreference());

    const persona = useMemo(
        () => preference ?? resolveNavPersona(ctx),
        [preference, ctx.isAdmin, ctx.workspaceRole],
    );

    const setPersona = useCallback(
        (next: NavPersona) => {
            writeNavPersonaPreference(next);
            setPreference(next);
        },
        [],
    );

    const resetPersona = useCallback(() => {
        try {
            localStorage.removeItem(NAV_PERSONA_STORAGE_KEY);
        } catch {
            // Ignore persistence failures.
        }
        setPreference(null);
    }, []);

    const isOverridden = preference !== null;

    return {
        persona,
        derivedPersona: derived,
        setPersona,
        resetPersona,
        isOverridden,
    };
}
