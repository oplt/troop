import type { ToastOptions } from "./snackbarContext";
import { extractApiErrorMessage } from "../utils/apiErrors";

type ShowToast = (opts: ToastOptions) => void;

/** Standard mutation success toast. Prefer this over stacking Alert banners. */
export function toastSuccess(showToast: ShowToast, message: string) {
    showToast({ message, severity: "success" });
}

/** Standard mutation / query failure toast with API message extraction. */
export function toastError(showToast: ShowToast, error: unknown, fallback: string) {
    showToast({
        message: extractApiErrorMessage(error, fallback),
        severity: "error",
    });
}

export function mutationToastHandlers(
    showToast: ShowToast,
    successMessage: string,
    errorFallback: string,
) {
    return {
        onSuccess: () => toastSuccess(showToast, successMessage),
        onError: (error: unknown) => toastError(showToast, error, errorFallback),
    };
}
