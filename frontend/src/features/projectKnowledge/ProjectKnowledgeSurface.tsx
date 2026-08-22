import { KnowledgeAskPanel } from "./KnowledgeAskPanel";
import { KnowledgeDocumentsPanel } from "./KnowledgeDocumentsPanel";

export function ProjectKnowledgeSurface({
    projectId,
    view,
}: {
    projectId: string;
    view: "documents" | "ask";
}) {
    return view === "documents"
        ? <KnowledgeDocumentsPanel projectId={projectId} />
        : <KnowledgeAskPanel projectId={projectId} />;
}
