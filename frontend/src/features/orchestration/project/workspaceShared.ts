import type { TaskRun } from "../../../api/orchestration";

export type ExecutionMode = "single_agent" | "manager_worker" | "debate";

export type LocalRepoDraft = {
    enabled: boolean;
    repo_path: string;
    dirty_worktree_policy: string;
    allowed_branches: string;
    file_allowlist: string;
    file_denylist: string;
    command_allowlist: string;
    max_diff_bytes: string;
};

export function splitCsv(value: string) {
    return value
        .split(/[,\n]/)
        .map((item) => item.trim())
        .filter(Boolean);
}

export function toastQueuedRunWithOptionalWarnings(
    showToast: (opts: { message: string; severity: "success" | "error" | "warning" | "info" }) => void,
    run: TaskRun,
    successLine: string,
) {
    const w = run.startup_warnings ?? [];
    if (w.length) {
        showToast({ message: `${successLine} ${w.join(" ")}`, severity: "warning" });
    } else {
        showToast({ message: successLine, severity: "success" });
    }
}
