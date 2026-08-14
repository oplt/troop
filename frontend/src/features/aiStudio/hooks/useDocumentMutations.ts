import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { createAiDocument, uploadAiDocument } from "../../../api/ai";
import { useSnackbar } from "../../../app/snackbarContext";
import type { TextDocumentFormState } from "../types";

export function useDocumentMutations() {
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();

    const [textDocumentForm, setTextDocumentForm] = useState<TextDocumentFormState>({
        title: "",
        description: "",
        content: "",
        content_type: "text/plain",
    });
    const [uploadDescription, setUploadDescription] = useState("");

    const createTextDocumentMutation = useMutation({
        mutationFn: createAiDocument,
        onSuccess: async (result) => {
            setTextDocumentForm({ title: "", description: "", content: "", content_type: "text/plain" });
            await queryClient.invalidateQueries({ queryKey: ["ai"] });
            showToast({
                message: result.queued ? "Document queued for indexing." : "Document ingested.",
                severity: "success",
            });
        },
    });

    const uploadDocumentMutation = useMutation({
        mutationFn: ({ file, description }: { file: File; description?: string }) =>
            uploadAiDocument(file, description),
        onSuccess: async (result) => {
            setUploadDescription("");
            await queryClient.invalidateQueries({ queryKey: ["ai"] });
            showToast({
                message: result.queued
                    ? "Document uploaded and queued for indexing."
                    : "Document uploaded and chunked.",
                severity: "success",
            });
        },
    });

    return {
        textDocumentForm,
        setTextDocumentForm,
        uploadDescription,
        setUploadDescription,
        createTextDocumentMutation,
        uploadDocumentMutation,
    };
}
