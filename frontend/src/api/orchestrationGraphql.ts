import { apiFetch } from "./client";

type GraphqlEnvelope<T> = {
    data?: T;
    errors?: Array<{ message: string }>;
};

export type OperatingModelProfile = {
    id: string;
    provider_config_id: string | null;
    provider_name: string | null;
    provider_type: string | null;
    model_slug: string;
    display_name: string;
    temperature: number | null;
    max_tokens: number | null;
    supports_tools: boolean;
    supports_structured_output: boolean;
    max_context_tokens: number | null;
    is_fallback: boolean;
};

export type OperatingTask = {
    id: string;
    title: string;
    description: string | null;
    status: string;
    priority: string;
    task_type: string;
    acceptance_criteria: string | null;
    result_summary: string | null;
    labels: string[];
    updated_at: string;
    pending_approval_count: number;
};

export type OperatingRun = {
    id: string;
    status: string;
    run_mode: string;
    model_name: string | null;
    token_total: number;
    estimated_cost_micros: number;
    latency_ms: number | null;
    error_message: string | null;
    created_at: string;
    started_at: string | null;
    completed_at: string | null;
};

export type OperatingMember = {
    id: string;
    parent_id: string | null;
    membership_id: string | null;
    name: string;
    role: string;
    objective: string | null;
    skills: string[];
    instructions: string;
    tool_access: string[];
    memory_scope: string;
    memory_policy: Record<string, unknown>;
    autonomy_level: string;
    approval_policy: string;
    current_status: string;
    workload_count: number;
    active_task_count: number;
    is_active: boolean;
    model_profile: OperatingModelProfile | null;
    fallback_model_profile: OperatingModelProfile | null;
    routing_policy: Record<string, unknown>;
    tasks: OperatingTask[];
    runs: OperatingRun[];
    runtime_profile: Record<string, unknown>;
};

export type OperatingApproval = {
    id: string;
    task_id: string | null;
    run_id: string | null;
    approval_type: string;
    status: string;
    reason: string | null;
    created_at: string;
};

export type OperatingBrainstorm = {
    id: string;
    topic: string;
    status: string;
    participant_count: number;
    current_round: number;
    consensus_status: string;
    updated_at: string;
};

export type OperatingHierarchySnapshot = {
    project: {
        id: string;
        name: string;
        status: string;
        goals_markdown: string;
        memory_scope: string;
        updated_at: string;
    };
    manager_id: string | null;
    members: OperatingMember[];
    pending_approvals: OperatingApproval[];
    brainstorms: OperatingBrainstorm[];
};

export type TeamMemberInput = {
    project_id: string;
    name?: string;
    role?: string;
    objective?: string;
    instructions?: string;
    skills?: string[];
    tool_access?: string[];
    memory_scope?: string;
    memory_policy?: Record<string, unknown>;
    autonomy_level?: string;
    approval_policy?: string;
    parent_member_id?: string | null;
    model_profile?: Record<string, unknown> | null;
    fallback_model_profile?: Record<string, unknown> | null;
    routing_policy?: Record<string, unknown> | unknown[] | null;
    is_active?: boolean;
    is_manager?: boolean;
};

export type TaskInput = {
    project_id: string;
    title: string;
    description?: string;
    assigned_member_id?: string | null;
    reviewer_member_id?: string | null;
    acceptance_criteria?: string;
    priority?: string;
    task_type?: string;
    labels?: string[];
    metadata?: Record<string, unknown>;
};

async function graphqlFetch<T>(query: string, variables?: Record<string, unknown>) {
    const response = await apiFetch<GraphqlEnvelope<T>>("/graphql", {
        method: "POST",
        body: JSON.stringify({ query, variables }),
    });
    if (response.errors?.length) {
        throw new Error(response.errors.map((item) => item.message).join(" "));
    }
    if (!response.data) {
        throw new Error("GraphQL response missing data.");
    }
    return response.data;
}

const SNAPSHOT_FIELDS = `
    project { id name status goals_markdown memory_scope updated_at }
    manager_id
    pending_approvals { id task_id run_id approval_type status reason created_at }
    brainstorms { id topic status participant_count current_round consensus_status updated_at }
    members {
        id
        parent_id
        membership_id
        name
        role
        objective
        skills
        instructions
        tool_access
        memory_scope
        memory_policy
        autonomy_level
        approval_policy
        current_status
        workload_count
        active_task_count
        is_active
        routing_policy
        runtime_profile
        model_profile {
            id
            provider_config_id
            provider_name
            provider_type
            model_slug
            display_name
            temperature
            max_tokens
            supports_tools
            supports_structured_output
            max_context_tokens
            is_fallback
        }
        fallback_model_profile {
            id
            provider_config_id
            provider_name
            provider_type
            model_slug
            display_name
            temperature
            max_tokens
            supports_tools
            supports_structured_output
            max_context_tokens
            is_fallback
        }
        tasks {
            id
            title
            description
            status
            priority
            task_type
            acceptance_criteria
            result_summary
            labels
            updated_at
            pending_approval_count
        }
        runs {
            id
            status
            run_mode
            model_name
            token_total
            estimated_cost_micros
            latency_ms
            error_message
            created_at
            started_at
            completed_at
        }
    }
`;

export async function fetchOperatingHierarchy(projectId: string) {
    const data = await graphqlFetch<{ hierarchy: OperatingHierarchySnapshot }>(
        `query Hierarchy($projectId: String!) {
            hierarchy(project_id: $projectId) {
                ${SNAPSHOT_FIELDS}
            }
        }`,
        { projectId },
    );
    return data.hierarchy;
}

export async function fetchOperatingModelProfiles(projectId: string) {
    const data = await graphqlFetch<{ model_profiles: OperatingModelProfile[] }>(
        `query ModelProfiles($projectId: String!) {
            model_profiles(project_id: $projectId) {
                id
                provider_config_id
                provider_name
                provider_type
                model_slug
                display_name
                temperature
                max_tokens
                supports_tools
                supports_structured_output
                max_context_tokens
                is_fallback
            }
        }`,
        { projectId },
    );
    return data.model_profiles;
}

export async function createTeamMember(input: TeamMemberInput) {
    const data = await graphqlFetch<{ create_team_member: OperatingMember }>(
        `mutation CreateTeamMember($input: TeamMemberInput!) {
            create_team_member(input: $input) {
                id
                name
                role
                current_status
                active_task_count
                model_profile { id display_name model_slug provider_name provider_type temperature max_tokens supports_tools supports_structured_output max_context_tokens is_fallback provider_config_id }
                fallback_model_profile { id display_name model_slug provider_name provider_type temperature max_tokens supports_tools supports_structured_output max_context_tokens is_fallback provider_config_id }
            }
        }`,
        { input },
    );
    return data.create_team_member;
}

export async function updateTeamMember(memberId: string, input: TeamMemberInput) {
    const data = await graphqlFetch<{ update_team_member: OperatingMember }>(
        `mutation UpdateTeamMember($memberId: String!, $input: TeamMemberInput!) {
            update_team_member(memberId: $memberId, input: $input) {
                id
                name
                role
                current_status
                active_task_count
                model_profile { id display_name model_slug provider_name provider_type temperature max_tokens supports_tools supports_structured_output max_context_tokens is_fallback provider_config_id }
                fallback_model_profile { id display_name model_slug provider_name provider_type temperature max_tokens supports_tools supports_structured_output max_context_tokens is_fallback provider_config_id }
            }
        }`,
        { memberId, input },
    );
    return data.update_team_member;
}

export async function removeTeamMember(projectId: string, memberId: string) {
    const data = await graphqlFetch<{ remove_team_member: boolean }>(
        `mutation RemoveTeamMember($projectId: String!, $memberId: String!) {
            remove_team_member(project_id: $projectId, memberId: $memberId)
        }`,
        { projectId, memberId },
    );
    return data.remove_team_member;
}

export async function createHierarchyTask(input: TaskInput) {
    const data = await graphqlFetch<{ create_hierarchy_task: OperatingTask }>(
        `mutation CreateHierarchyTask($input: TaskInput!) {
            create_hierarchy_task(input: $input) {
                id
                title
                description
                status
                priority
                task_type
                acceptance_criteria
                result_summary
                labels
                updated_at
                pending_approval_count
            }
        }`,
        { input },
    );
    return data.create_hierarchy_task;
}

export async function assignHierarchyTask(projectId: string, taskId: string, memberId: string) {
    const data = await graphqlFetch<{ assign_task: OperatingTask }>(
        `mutation AssignTask($projectId: String!, $taskId: String!, $memberId: String!) {
            assign_task(project_id: $projectId, taskId: $taskId, memberId: $memberId) {
                id
                title
                description
                status
                priority
                task_type
                acceptance_criteria
                result_summary
                labels
                updated_at
                pending_approval_count
            }
        }`,
        { projectId, taskId, memberId },
    );
    return data.assign_task;
}

export async function requestTaskRevision(projectId: string, taskId: string, notes: string) {
    const data = await graphqlFetch<{ request_task_revision: OperatingTask }>(
        `mutation RequestTaskRevision($projectId: String!, $taskId: String!, $notes: String!) {
            request_task_revision(project_id: $projectId, taskId: $taskId, notes: $notes) {
                id
                title
                description
                status
                priority
                task_type
                acceptance_criteria
                result_summary
                labels
                updated_at
                pending_approval_count
            }
        }`,
        { projectId, taskId, notes },
    );
    return data.request_task_revision;
}

export async function approveTaskOutput(projectId: string, taskId: string, summary?: string) {
    const data = await graphqlFetch<{ approve_task_output: OperatingTask }>(
        `mutation ApproveTaskOutput($projectId: String!, $taskId: String!, $summary: String) {
            approve_task_output(project_id: $projectId, taskId: $taskId, summary: $summary) {
                id
                title
                description
                status
                priority
                task_type
                acceptance_criteria
                result_summary
                labels
                updated_at
                pending_approval_count
            }
        }`,
        { projectId, taskId, summary },
    );
    return data.approve_task_output;
}

export async function launchHierarchyTaskRun(projectId: string, taskId: string, memberId?: string) {
    const data = await graphqlFetch<{ launch_task_run: OperatingRun }>(
        `mutation LaunchTaskRun($projectId: String!, $taskId: String!, $memberId: String) {
            launch_task_run(project_id: $projectId, taskId: $taskId, memberId: $memberId) {
                id
                status
                run_mode
                model_name
                token_total
                estimated_cost_micros
                latency_ms
                error_message
                created_at
                started_at
                completed_at
            }
        }`,
        { projectId, taskId, memberId },
    );
    return data.launch_task_run;
}

export async function startHierarchyBrainstorm(
    projectId: string,
    topic: string,
    participantIds: string[],
    taskId?: string,
) {
    const data = await graphqlFetch<{ start_brainstorm: OperatingBrainstorm }>(
        `mutation StartBrainstorm($projectId: String!, $topic: String!, $participantIds: [String!]!, $taskId: String) {
            start_brainstorm(project_id: $projectId, topic: $topic, participantIds: $participantIds, taskId: $taskId) {
                id
                topic
                status
                participant_count
                current_round
                consensus_status
                updated_at
            }
        }`,
        { projectId, topic, participantIds, taskId },
    );
    return data.start_brainstorm;
}
