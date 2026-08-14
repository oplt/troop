import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Box } from "@mui/material";
import { Storage as StorageIcon } from "@mui/icons-material";

import {
    createDatabaseSetting,
    deleteDatabaseSetting,
    listParameterCatalog,
    updateDatabaseSetting,
    type DatabaseSetting,
} from "../../../api/settings";
import { ConfirmDestructiveDialog } from "../../../components/ui/ConfirmDestructiveDialog";
import { EmptyState } from "../../../components/ui/EmptyState";
import { SectionCard } from "../../../components/ui/SectionCard";
import type { DatabaseSettingDrafts, NewDatabaseSettingForm, ParameterCatalogMap } from "../types";
import { CreateDatabaseSettingForm } from "./CreateDatabaseSettingForm";
import { DatabaseSettingEditor } from "./DatabaseSettingEditor";

type DatabaseSettingsPanelProps = {
    settings: DatabaseSetting[];
    onDirtyChange?: (dirty: boolean) => void;
};

export function DatabaseSettingsPanel({ settings, onDirtyChange }: DatabaseSettingsPanelProps) {
    const queryClient = useQueryClient();
    const { data: parameterCatalog = [] } = useQuery({
        queryKey: ["settings", "database", "catalog"],
        queryFn: listParameterCatalog,
    });

    const [databaseDrafts, setDatabaseDrafts] = useState<DatabaseSettingDrafts>(() =>
        Object.fromEntries(
            settings.map((item) => [
                item.id,
                {
                    value: item.value,
                    description: item.description ?? "",
                },
            ]),
        ),
    );
    const [newSetting, setNewSetting] = useState<NewDatabaseSettingForm>({
        key: "",
        value: "",
        description: "",
    });
    const [deleteTarget, setDeleteTarget] = useState<DatabaseSetting | null>(null);

    const parameterCatalogMap: ParameterCatalogMap = useMemo(
        () => Object.fromEntries(parameterCatalog.map((item) => [item.key, item])),
        [parameterCatalog],
    );
    const selectedParameterSpec = parameterCatalogMap[newSetting.key] ?? null;

    const databaseDirty = settings.some((item) => {
        const draft = databaseDrafts[item.id];
        if (!draft) return false;
        return draft.value !== item.value || draft.description !== (item.description ?? "");
    });

    useEffect(() => {
        onDirtyChange?.(databaseDirty);
    }, [databaseDirty, onDirtyChange]);

    const createDatabaseMutation = useMutation({
        mutationFn: createDatabaseSetting,
        onSuccess: async () => {
            setNewSetting({ key: "", value: "", description: "" });
            await queryClient.invalidateQueries({ queryKey: ["settings", "database"] });
        },
    });
    const updateDatabaseMutation = useMutation({
        mutationFn: ({ id, value, description }: { id: string; value: string; description: string }) =>
            updateDatabaseSetting(id, { value, description }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["settings", "database"] });
        },
    });
    const deleteDatabaseMutation = useMutation({
        mutationFn: deleteDatabaseSetting,
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["settings", "database"] });
        },
    });

    return (
        <>
            <Box
                sx={{
                    display: "grid",
                    gap: 2,
                    gridTemplateColumns: { xs: "1fr", lg: "minmax(320px, 0.9fr) minmax(0, 1.1fr)" },
                    alignItems: "start",
                }}
            >
                <SectionCard
                    title="Add parameter"
                    description="Create typed runtime parameters from the supported catalog."
                >
                    <CreateDatabaseSettingForm
                        form={newSetting}
                        parameterCatalog={parameterCatalog}
                        selectedSpec={selectedParameterSpec}
                        isCreating={createDatabaseMutation.isPending}
                        createSucceeded={createDatabaseMutation.isSuccess}
                        createError={createDatabaseMutation.error}
                        onFormChange={setNewSetting}
                        onCreate={() =>
                            createDatabaseMutation.mutate({
                                key: newSetting.key.trim(),
                                value: newSetting.value,
                                description: newSetting.description || undefined,
                            })
                        }
                    />
                </SectionCard>

                <SectionCard
                    title="Parameters"
                    description="Review, edit, and delete runtime parameters stored in the database."
                >
                    {settings.length > 0 ? (
                        <Box
                            sx={{
                                display: "grid",
                                gap: 1.5,
                                gridTemplateColumns: { xs: "1fr", xl: "repeat(2, minmax(0, 1fr))" },
                                alignItems: "start",
                            }}
                        >
                            {settings.map((item) => {
                                const isSavingThisItem =
                                    updateDatabaseMutation.isPending &&
                                    updateDatabaseMutation.variables?.id === item.id;
                                const isDeletingThisItem =
                                    deleteDatabaseMutation.isPending &&
                                    deleteDatabaseMutation.variables === item.id;

                                return (
                                    <DatabaseSettingEditor
                                        key={item.id}
                                        item={item}
                                        spec={parameterCatalogMap[item.key] ?? null}
                                        draft={
                                            databaseDrafts[item.id] ?? {
                                                value: item.value,
                                                description: item.description ?? "",
                                            }
                                        }
                                        onDraftChange={(nextDraft) =>
                                            setDatabaseDrafts((current) => ({
                                                ...current,
                                                [item.id]: nextDraft,
                                            }))
                                        }
                                        onSave={() =>
                                            updateDatabaseMutation.mutate({
                                                id: item.id,
                                                value: databaseDrafts[item.id]?.value ?? item.value,
                                                description:
                                                    databaseDrafts[item.id]?.description ?? item.description ?? "",
                                            })
                                        }
                                        onDelete={() => setDeleteTarget(item)}
                                        isSaving={isSavingThisItem}
                                        isDeleting={isDeletingThisItem}
                                    />
                                );
                            })}
                        </Box>
                    ) : (
                        <EmptyState
                            icon={<StorageIcon />}
                            title="No parameters yet"
                            description="Create a parameter when you need runtime-configurable values stored in the database."
                        />
                    )}
                </SectionCard>
            </Box>

            <ConfirmDestructiveDialog
                open={Boolean(deleteTarget)}
                title="Delete parameter"
                description={
                    deleteTarget
                        ? `Remove “${deleteTarget.key}”? Runtime code that reads this key will fall back to defaults.`
                        : ""
                }
                confirmLabel="Delete"
                loading={deleteDatabaseMutation.isPending}
                onClose={() => setDeleteTarget(null)}
                onConfirm={() => {
                    if (!deleteTarget) return;
                    deleteDatabaseMutation.mutate(deleteTarget.id, {
                        onSettled: () => setDeleteTarget(null),
                    });
                }}
            />
        </>
    );
}
