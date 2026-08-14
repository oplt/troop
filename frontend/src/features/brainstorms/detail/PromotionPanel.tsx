import { Button, Stack } from "@mui/material";
import {
    Assignment as TaskIcon,
    Description as DocumentIcon,
    Rule as AdrIcon,
} from "@mui/icons-material";

import type { Brainstorm } from "../../../api/orchestration";

type PromotionPanelProps = {
    brainstorm: Brainstorm;
    isPromotingTasks: boolean;
    isPromotingAdr: boolean;
    isPromotingDocument: boolean;
    isExporting: boolean;
    onPromoteTasks: () => void;
    onPromoteAdr: () => void;
    onPromoteDocument: () => void;
    onExportArtifact: () => void;
    onOpenProject: () => void;
};

export function PromotionPanel({
    brainstorm,
    isPromotingTasks,
    isPromotingAdr,
    isPromotingDocument,
    isExporting,
    onPromoteTasks,
    onPromoteAdr,
    onPromoteDocument,
    onExportArtifact,
    onOpenProject,
}: PromotionPanelProps) {
    return (
        <Stack spacing={1}>
            <Button
                startIcon={<TaskIcon />}
                variant="contained"
                onClick={onPromoteTasks}
                disabled={isPromotingTasks}
            >
                Promote to task
            </Button>
            <Button startIcon={<AdrIcon />} variant="outlined" onClick={onPromoteAdr} disabled={isPromotingAdr}>
                Promote to ADR
            </Button>
            <Button
                startIcon={<DocumentIcon />}
                variant="outlined"
                onClick={onPromoteDocument}
                disabled={isPromotingDocument}
            >
                Promote to project document
            </Button>
            <Button
                startIcon={<DocumentIcon />}
                variant="outlined"
                onClick={onExportArtifact}
                disabled={isExporting || !brainstorm.final_recommendation}
            >
                Export as first-class artifact
            </Button>
            {brainstorm.project_id && (
                <Button variant="text" onClick={onOpenProject}>
                    Open project
                </Button>
            )}
        </Stack>
    );
}
