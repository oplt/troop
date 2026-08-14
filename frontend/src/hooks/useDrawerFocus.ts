import { useEffect, useRef, type RefObject } from "react";

function firstFocusable(root: HTMLElement | null): HTMLElement | null {
    if (!root) return null;
    const nodes = root.querySelectorAll<HTMLElement>(
        'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    );
    return nodes[0] ?? null;
}

/**
 * On drawer/dialog open: focus first focusable inside the panel.
 * On close: restore focus to the element that opened it (if still mounted).
 */
export function useDrawerFocus(open: boolean, panelRef: RefObject<HTMLElement | null>) {
    const triggerRef = useRef<HTMLElement | null>(null);

    useEffect(() => {
        if (open) {
            const active = document.activeElement;
            if (active instanceof HTMLElement) {
                triggerRef.current = active;
            }
            const frame = window.requestAnimationFrame(() => {
                firstFocusable(panelRef.current)?.focus();
            });
            return () => window.cancelAnimationFrame(frame);
        }

        const trigger = triggerRef.current;
        if (trigger && document.contains(trigger)) {
            const frame = window.requestAnimationFrame(() => {
                trigger.focus();
            });
            triggerRef.current = null;
            return () => window.cancelAnimationFrame(frame);
        }
        return undefined;
    }, [open, panelRef]);
}
