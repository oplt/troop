export type AiProvider = {
    key: string;
    label: string;
    supports_generation: boolean;
    supports_embeddings: boolean;
};

export type AiPromptTemplate = {
    id: string;
    key: string;
    name: string;
    description: string | null;
    is_active: boolean;
    active_version_id: string | null;
    created_at: string;
    updated_at: string;
};

export type AiVariableDefinition = {
    name: string;
    description: string | null;
    required: boolean;
};

export type AiPromptVersion = {
    id: string;
    prompt_template_id: string;
    version_number: number;
    provider_key: string;
    model_name: string;
    system_prompt: string;
    user_prompt_template: string;
    variable_definitions: AiVariableDefinition[];
    response_format: "text" | "json";
    temperature: number;
    rollout_percentage: number;
    is_published: boolean;
    input_cost_per_million: number;
    output_cost_per_million: number;
    created_by_user_id: string | null;
    created_at: string;
};

export type AiDocument = {
    id: string;
    title: string;
    description: string | null;
    filename: string | null;
    content_type: string;
    size_bytes: number;
    ingestion_status: string;
    metadata: Record<string, unknown>;
    chunk_count: number;
    created_at: string;
    updated_at: string;
};

export type AiDocumentIngestResponse = {
    document: AiDocument;
    ingest_job_id: string | null;
    queued: boolean;
};

export type AiRun = {
    id: string;
    prompt_template_id: string | null;
    prompt_version_id: string | null;
    provider_key: string;
    model_name: string;
    status: string;
    response_format: string;
    variables: Record<string, unknown>;
    retrieval_query: string | null;
    retrieved_chunk_ids: string[];
    input_messages: Array<{ role: string; content: string }>;
    output_text: string | null;
    output_json: Record<string, unknown> | null;
    latency_ms: number | null;
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
    estimated_cost_micros: number;
    error_message: string | null;
    review_status: string;
    created_at: string;
    completed_at: string | null;
};

export type AiReviewItem = {
    id: string;
    run_id: string;
    requested_by_user_id: string;
    assigned_to_user_id: string | null;
    reviewed_by_user_id: string | null;
    status: string;
    reviewer_notes: string | null;
    corrected_output: string | null;
    created_at: string;
    updated_at: string;
};

export type AiFeedback = {
    id: string;
    run_id: string;
    user_id: string;
    rating: number;
    comment: string | null;
    corrected_output: string | null;
    created_at: string;
};

export type AiEvaluationDataset = {
    id: string;
    name: string;
    description: string | null;
    created_at: string;
    updated_at: string;
};

export type AiEvaluationCase = {
    id: string;
    dataset_id: string;
    input_variables: Record<string, unknown>;
    expected_output_text: string | null;
    expected_output_json: Record<string, unknown> | null;
    expected_assertions: Record<string, unknown> | null;
    notes: string | null;
    source_run_id: string | null;
    source_trace_span_id: string | null;
    provenance: Record<string, unknown>;
    input_snapshot: Record<string, unknown>;
    correction: Record<string, unknown> | null;
    created_at: string;
};

export type AiEvaluationRunItem = {
    evaluation_case_id: string;
    ai_run_id: string;
    score: number;
    passed: boolean;
    notes: string | null;
    metrics?: Record<string, unknown>;
};

export type AiEvaluationScorecard = {
    candidate: Record<string, unknown>;
    metrics: Record<string, unknown>;
    baseline_metrics?: Record<string, unknown> | null;
    regression: {
        detected?: boolean;
        threshold?: number;
        baseline_pass_rate?: number | null;
        candidate_pass_rate?: number;
        delta_pass_rate?: number | null;
        publish_recommendation?: "approve" | "review" | "block";
    };
    judge: { version_id?: string | null; mode?: string };
};

export type AiEvaluationRun = {
    id: string;
    dataset_id: string;
    prompt_version_id: string;
    status: string;
    total_cases: number;
    passed_cases: number;
    average_score: number;
    baseline_run_id?: string | null;
    candidate_config?: Record<string, unknown>;
    metrics?: Record<string, unknown>;
    scorecard?: AiEvaluationScorecard;
    judge_version_id?: string | null;
    created_at: string;
    completed_at: string | null;
    items: AiEvaluationRunItem[];
};

export type AiOverview = {
    providers: AiProvider[];
    recent_runs: AiRun[];
    prompt_template_count: number;
    document_count: number;
    pending_review_count: number;
    dataset_count: number;
};

export type AiChunkMatch = {
    document_id: string;
    chunk_id: string;
    document_title: string;
    chunk_index: number;
    score: number;
    content: string;
};
