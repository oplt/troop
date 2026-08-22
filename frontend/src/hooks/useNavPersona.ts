import { useCallback, useState } from "react";

import type { NavPersona } from "../components/layout/navConfig";
import {
    deriveNavPersona,
    NAV_PERSONA_STORAGE_KEY,
    readNavPersonaPreference,
    resolveNavPersona,
    writeNavPersonaPreference,
    type NavPersonaContext,
} from "../components/layout/navPersona";

export function useNavPersona(ctx: NavPersonaContext) {
    const derived = deriveNavPersona(ctx);
    const [preference, setPreference] = useState<NavPersona | null>(() => readNavPersonaPreference());
    const persona = preference ?? resolveNavPersona(ctx);

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
