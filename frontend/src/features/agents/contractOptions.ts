/**
 * Shared agent contract select options (permissions, memory, output schema).
 * Single source for AgentProfiles, Hierarchy forms, and templates.
 */
export const PERMISSION_OPTIONS = ["read-only", "comment-only", "code-write", "merge-blocked"] as const;
export const MEMORY_SCOPE_OPTIONS = ["none", "project-only", "long-term"] as const;
export const OUTPUT_FORMAT_OPTIONS = ["checklist", "json", "patch_proposal", "issue_reply", "adr"] as const;

export type PermissionOption = (typeof PERMISSION_OPTIONS)[number];
export type MemoryScopeOption = (typeof MEMORY_SCOPE_OPTIONS)[number];
export type OutputFormatOption = (typeof OUTPUT_FORMAT_OPTIONS)[number];

/** Legacy aliases used by AgentProfiles selects. */
export const PERMISSIONS = PERMISSION_OPTIONS;
export const MEMORIES = MEMORY_SCOPE_OPTIONS;
export const OUTPUTS = OUTPUT_FORMAT_OPTIONS;
