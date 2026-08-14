import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import {
    createPromptTemplate,
    createPromptVersion,
    updatePromptTemplate,
    updatePromptVersion,
} from "../../../api/ai";
import { useSnackbar } from "../../../app/snackbarContext";
import type { TemplateFormState, VersionFormState } from "../types";

type UsePromptMutationsOptions = {
    selectedTemplateId: string;
};

export function usePromptMutations({ selectedTemplateId }: UsePromptMutationsOptions) {
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();

    const [templateForm, setTemplateForm] = useState<TemplateFormState>({ key: "", name: "", description: "" });
    const [versionForm, setVersionForm] = useState<VersionFormState>({
        provider_key: "local",
        model_name: "local-heuristic",
        system_prompt: "",
        user_prompt_template: "",
        variable_names: "",
        response_format: "text",
        temperature: "0.2",
        rollout_percentage: "100",
        is_published: true,
        input_cost_per_million: "0",
        output_cost_per_million: "0",
    });

    const createTemplateMutation = useMutation({
        mutationFn: createPromptTemplate,
        onSuccess: async () => {
            setTemplateForm({ key: "", name: "", description: "" });
            await queryClient.invalidateQueries({ queryKey: ["ai"] });
            showToast({ message: "Prompt template created.", severity: "success" });
        },
    });

    const createVersionMutation = useMutation({
        mutationFn: ({
            templateId,
            payload,
        }: {
            templateId: string;
            payload: Parameters<typeof createPromptVersion>[1];
        }) => createPromptVersion(templateId, payload),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["ai"] });
            await queryClient.invalidateQueries({ queryKey: ["ai", "prompt-versions", selectedTemplateId] });
            showToast({ message: "Prompt version created.", severity: "success" });
        },
    });

    const activateVersionMutation = useMutation({
        mutationFn: ({ templateId, versionId }: { templateId: string; versionId: string }) =>
            updatePromptTemplate(templateId, { active_version_id: versionId }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["ai"] });
            showToast({ message: "Active prompt version updated.", severity: "success" });
        },
    });

    const publishVersionMutation = useMutation({
        mutationFn: ({
            templateId,
            versionId,
            isPublished,
        }: {
            templateId: string;
            versionId: string;
            isPublished: boolean;
        }) => updatePromptVersion(templateId, versionId, { is_published: isPublished }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["ai", "prompt-versions", selectedTemplateId] });
            showToast({ message: "Prompt version updated.", severity: "success" });
        },
    });

    return {
        templateForm,
        setTemplateForm,
        versionForm,
        setVersionForm,
        createTemplateMutation,
        createVersionMutation,
        activateVersionMutation,
        publishVersionMutation,
    };
}
