import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Box,
    Button,
    Chip,
    CircularProgress,
    Divider,
    LinearProgress,
    List,
    ListItem,
    ListItemText,
    Paper,
    Stack,
    Typography,
} from "@mui/material";
import {
    Analytics as AnalyzeIcon,
    AutoAwesome as GenerateIcon,
    Psychology as AgentIcon,
    EmojiObjects as SkillsIcon,
    CheckCircle as CheckCircleIcon,
    Cancel as CancelIcon,
} from "@mui/icons-material";
import {
    analyzeTask,
    assembleAgent,
    findAgentMatches,
    findSkillMatches,
    generateMissingSkills,
    getLastSkillGap,
    getTaskAnalysis,
    type AgentMatch,
    type GeneratedSkillDraft,
    type SkillMatch,
} from "../../api/workforce";
import { useSnackbar } from "../../app/snackbarContext";

type TaskIntelligencePanelProps = {
    projectId: string;
    taskId: string;
};

export function TaskIntelligencePanel({ taskId }: TaskIntelligencePanelProps) {
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();

    const { data: analysis } = useQuery({
        queryKey: ["workforce", "task-analysis", taskId],
        queryFn: () => getTaskAnalysis(taskId),
        retry: false,
        enabled: Boolean(taskId),
    });

    const {
        data: skillMatches,
        isLoading: isLoadingSkills,
    } = useQuery<SkillMatch[]>({
        queryKey: ["workforce", "skill-matches", taskId],
        queryFn: () => findSkillMatches(taskId),
        enabled: false,
    });

    const {
        data: generatedDrafts,
        isLoading: isLoadingGenerated,
    } = useQuery<GeneratedSkillDraft[]>({
        queryKey: ["workforce", "generated-skills", taskId],
        queryFn: () => generateMissingSkills(taskId),
        enabled: false,
    });

    const {
        data: agentMatches,
        isLoading: isLoadingAgents,
    } = useQuery<AgentMatch[]>({
        queryKey: ["workforce", "agent-matches", taskId],
        queryFn: () => findAgentMatches(taskId),
        enabled: false,
    });

    const analyzeMutation = useMutation({
        mutationFn: () => analyzeTask(taskId),
        onSuccess: (data) => {
            queryClient.setQueryData(["workforce", "task-analysis", taskId], data);
            showToast({ message: "Task analyzed successfully", severity: "success" });
        },
        onError: (error: Error) => {
            showToast({ message: `Analysis failed: ${error.message}`, severity: "error" });
        },
    });

    const findSkillsMutation = useMutation({
        mutationFn: () => findSkillMatches(taskId),
        onSuccess: (data) => {
            queryClient.setQueryData(["workforce", "skill-matches", taskId], data);
            const gap = getLastSkillGap();
            if (gap && analysis) {
                queryClient.setQueryData(["workforce", "task-analysis", taskId], {
                    ...analysis,
                    covered_requirements: gap.covered.map((c) => c.capability),
                    missing_requirements: gap.missing.map((c) => c.capability),
                });
            }
            showToast({ message: "Found skill matches", severity: "success" });
        },
        onError: (error: Error) => {
            showToast({ message: `Skill search failed: ${error.message}`, severity: "error" });
        },
    });

    const generateSkillsMutation = useMutation({
        mutationFn: () => generateMissingSkills(taskId),
        onSuccess: (data) => {
            queryClient.setQueryData(["workforce", "generated-skills", taskId], data);
            showToast({ message: `Generated ${data.length} skill draft(s)`, severity: "success" });
        },
        onError: (error: Error) => {
            showToast({ message: `Generation failed: ${error.message}`, severity: "error" });
        },
    });

    const recommendAgentMutation = useMutation({
        mutationFn: () => findAgentMatches(taskId),
        onSuccess: (data) => {
            queryClient.setQueryData(["workforce", "agent-matches", taskId], data);
            showToast({ message: "Found agent recommendations", severity: "success" });
        },
        onError: (error: Error) => {
            showToast({ message: `Agent search failed: ${error.message}`, severity: "error" });
        },
    });

    const assembleAgentMutation = useMutation({
        mutationFn: () =>
            assembleAgent(taskId, {
                activate: true,
                assign_to_task: true,
            }),
        onSuccess: (data) => {
            const history = data.historical_success || "Not enough historical data";
            showToast({
                message: `Agent assembled: ${data.agent_name}. ${history}.`,
                severity: "success",
            });
        },
        onError: (error: Error) => {
            showToast({ message: `Assembly failed: ${error.message}`, severity: "error" });
        },
    });

    const isAnalyzing = analyzeMutation.isPending;
    const isFindingSkills = findSkillsMutation.isPending || isLoadingSkills;
    const isGeneratingSkills = generateSkillsMutation.isPending || isLoadingGenerated;
    const isRecommendingAgent = recommendAgentMutation.isPending || isLoadingAgents;
    const isAssemblingAgent = assembleAgentMutation.isPending;

    const hasAnalysis = Boolean(analysis);
    const hasSkillMatches = Boolean(skillMatches && skillMatches.length > 0);
    const hasGeneratedDrafts = Boolean(generatedDrafts && generatedDrafts.length > 0);
    const hasAgentMatches = Boolean(agentMatches && agentMatches.length > 0);

    return (
        <Paper
            elevation={0}
            sx={{ p: 3, border: (theme) => `1px solid ${theme.palette.divider}` }}
        >
            <Stack spacing={3}>
                <Box>
                    <Typography variant="h6" gutterBottom>
                        Task Intelligence
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                        AI-powered analysis to understand requirements, find skills, and recommend agents
                    </Typography>
                </Box>

                <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap>
                    <Button
                        variant={hasAnalysis ? "outlined" : "contained"}
                        startIcon={isAnalyzing ? <CircularProgress size={16} /> : <AnalyzeIcon />}
                        onClick={() => analyzeMutation.mutate()}
                        disabled={isAnalyzing}
                        size="small"
                    >
                        Analyze task
                    </Button>
                    <Button
                        variant={hasSkillMatches ? "outlined" : "contained"}
                        startIcon={isFindingSkills ? <CircularProgress size={16} /> : <SkillsIcon />}
                        onClick={() => findSkillsMutation.mutate()}
                        disabled={isFindingSkills}
                        size="small"
                    >
                        Find skills
                    </Button>
                    <Button
                        variant={hasGeneratedDrafts ? "outlined" : "contained"}
                        startIcon={isGeneratingSkills ? <CircularProgress size={16} /> : <GenerateIcon />}
                        onClick={() => generateSkillsMutation.mutate()}
                        disabled={isGeneratingSkills}
                        size="small"
                    >
                        Generate missing skills
                    </Button>
                    <Button
                        variant={hasAgentMatches ? "outlined" : "contained"}
                        startIcon={isRecommendingAgent ? <CircularProgress size={16} /> : <AgentIcon />}
                        onClick={() => recommendAgentMutation.mutate()}
                        disabled={isRecommendingAgent}
                        size="small"
                    >
                        Recommend agent
                    </Button>
                    <Button
                        variant="outlined"
                        startIcon={isAssemblingAgent ? <CircularProgress size={16} /> : <AgentIcon />}
                        onClick={() => assembleAgentMutation.mutate()}
                        disabled={isAssemblingAgent}
                        size="small"
                    >
                        Create agent
                    </Button>
                </Stack>

                {analysis && (
                    <>
                        <Divider />
                        <Stack spacing={2}>
                            <Typography variant="subtitle2" fontWeight={600}>
                                Analysis Results
                            </Typography>

                            <Box>
                                <Typography variant="caption" color="text.secondary" display="block" gutterBottom>
                                    Risk / Autonomy
                                </Typography>
                                <Stack direction="row" spacing={1} alignItems="center">
                                    <Chip label={`Risk: ${analysis.risk_level || analysis.risk_factors[0] || "medium"}`} size="small" />
                                    <Chip
                                        label={`Autonomy: ${analysis.autonomy_recommendation || "semi-autonomous"}`}
                                        size="small"
                                        variant="outlined"
                                    />
                                    {analysis.task_category ? (
                                        <Chip label={analysis.task_category} size="small" variant="outlined" />
                                    ) : null}
                                </Stack>
                            </Box>

                            {analysis.objective ? (
                                <Box>
                                    <Typography variant="caption" color="text.secondary">
                                        Objective: {analysis.objective}
                                    </Typography>
                                </Box>
                            ) : null}

                            {analysis.required_capabilities.length > 0 && (
                                <Box>
                                    <Typography variant="caption" color="text.secondary" display="block" gutterBottom>
                                        Required Capabilities
                                    </Typography>
                                    <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                                        {analysis.required_capabilities.map((cap) => (
                                            <Chip key={cap} label={cap} size="small" />
                                        ))}
                                    </Stack>
                                </Box>
                            )}

                            {analysis.covered_requirements.length > 0 && (
                                <Box>
                                    <Typography variant="caption" color="text.secondary" display="block" gutterBottom>
                                        Covered Requirements
                                    </Typography>
                                    <List dense disablePadding>
                                        {analysis.covered_requirements.map((req, idx) => (
                                            <ListItem key={idx} disableGutters>
                                                <CheckCircleIcon
                                                    fontSize="small"
                                                    color="success"
                                                    sx={{ mr: 1 }}
                                                />
                                                <ListItemText
                                                    primary={req}
                                                    primaryTypographyProps={{ variant: "body2" }}
                                                />
                                            </ListItem>
                                        ))}
                                    </List>
                                </Box>
                            )}

                            {analysis.missing_requirements.length > 0 && (
                                <Box>
                                    <Typography variant="caption" color="text.secondary" display="block" gutterBottom>
                                        Missing Requirements
                                    </Typography>
                                    <List dense disablePadding>
                                        {analysis.missing_requirements.map((req, idx) => (
                                            <ListItem key={idx} disableGutters>
                                                <CancelIcon
                                                    fontSize="small"
                                                    color="warning"
                                                    sx={{ mr: 1 }}
                                                />
                                                <ListItemText
                                                    primary={req}
                                                    primaryTypographyProps={{ variant: "body2" }}
                                                />
                                            </ListItem>
                                        ))}
                                    </List>
                                </Box>
                            )}

                            {analysis.risk_factors.length > 0 && (
                                <Box>
                                    <Typography variant="caption" color="text.secondary" display="block" gutterBottom>
                                        Risk Factors
                                    </Typography>
                                    <List dense disablePadding>
                                        {analysis.risk_factors.map((risk, idx) => (
                                            <ListItem key={idx} disableGutters>
                                                <ListItemText
                                                    primary={risk}
                                                    primaryTypographyProps={{ variant: "body2", color: "error" }}
                                                />
                                            </ListItem>
                                        ))}
                                    </List>
                                </Box>
                            )}
                        </Stack>
                    </>
                )}

                {skillMatches && skillMatches.length > 0 && (
                    <>
                        <Divider />
                        <Stack spacing={2}>
                            <Typography variant="subtitle2" fontWeight={600}>
                                Skill Matches ({skillMatches.length})
                            </Typography>
                            {skillMatches.map((match) => (
                                <Paper
                                    key={match.skill_id}
                                    variant="outlined"
                                    sx={{ p: 2 }}
                                >
                                    <Stack spacing={1}>
                                        <Stack direction="row" spacing={1} alignItems="center">
                                            <Typography variant="body2" fontWeight={600}>
                                                {match.skill_name}
                                            </Typography>
                                            <Chip
                                                label={match.skill_scope || match.scope}
                                                size="small"
                                                variant="outlined"
                                            />
                                            <Chip
                                                label={`${Math.round(match.match_score * 100)}% match`}
                                                size="small"
                                                color={match.match_score >= 0.8 ? "success" : match.match_score >= 0.6 ? "info" : "default"}
                                            />
                                        </Stack>
                                        <Typography variant="caption" color="text.secondary">
                                            {match.explanation}
                                        </Typography>
                                        {match.matched_capabilities.length > 0 && (
                                            <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                                                {match.matched_capabilities.map((cap) => (
                                                    <Chip key={cap} label={cap} size="small" />
                                                ))}
                                            </Stack>
                                        )}
                                        <LinearProgress
                                            variant="determinate"
                                            value={match.coverage_percentage ?? Math.round(match.match_score * 100)}
                                            sx={{ height: 4, borderRadius: 1 }}
                                        />
                                        <Typography variant="caption" color="text.secondary">
                                            {Math.round(match.coverage_percentage ?? match.match_score * 100)}% coverage
                                        </Typography>
                                    </Stack>
                                </Paper>
                            ))}
                        </Stack>
                    </>
                )}

                {generatedDrafts && generatedDrafts.length > 0 && (
                    <>
                        <Divider />
                        <Stack spacing={2}>
                            <Typography variant="subtitle2" fontWeight={600}>
                                Generated Skill Drafts ({generatedDrafts.length})
                            </Typography>
                            {generatedDrafts.map((draft) => (
                                <Paper
                                    key={draft.draft_id}
                                    variant="outlined"
                                    sx={{ p: 2 }}
                                >
                                    <Stack spacing={1}>
                                        <Stack direction="row" spacing={1} alignItems="center">
                                            <Typography variant="body2" fontWeight={600}>
                                                {draft.name}
                                            </Typography>
                                            <Chip
                                                label={
                                                    draft.confidence_score != null
                                                        ? `${Math.round(draft.confidence_score * 100)}% confidence`
                                                        : "Not evaluated"
                                                }
                                                size="small"
                                                color={
                                                    draft.confidence_score != null && draft.confidence_score >= 0.8
                                                        ? "success"
                                                        : "default"
                                                }
                                            />
                                        </Stack>
                                        <Typography variant="caption" color="text.secondary">
                                            {draft.purpose}
                                        </Typography>
                                        <Typography variant="caption" color="text.secondary" fontStyle="italic">
                                            {draft.reasoning}
                                        </Typography>
                                        {draft.capabilities.length > 0 && (
                                            <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                                                {draft.capabilities.map((cap) => (
                                                    <Chip key={cap} label={cap} size="small" />
                                                ))}
                                            </Stack>
                                        )}
                                        <Button
                                            size="small"
                                            href={`/skills/builder?draftId=${draft.draft_id}`}
                                            sx={{ alignSelf: "flex-start" }}
                                        >
                                            Edit draft
                                        </Button>
                                    </Stack>
                                </Paper>
                            ))}
                        </Stack>
                    </>
                )}

                {agentMatches && agentMatches.length > 0 && (
                    <>
                        <Divider />
                        <Stack spacing={2}>
                            <Typography variant="subtitle2" fontWeight={600}>
                                Agent Recommendations ({agentMatches.length})
                            </Typography>
                            {agentMatches.map((match) => (
                                <Paper
                                    key={match.agent_id}
                                    variant="outlined"
                                    sx={{ p: 2 }}
                                >
                                    <Stack spacing={1}>
                                        <Stack direction="row" spacing={1} alignItems="center">
                                            <Typography variant="body2" fontWeight={600}>
                                                {match.agent_name}
                                            </Typography>
                                            <Chip
                                                label={`${Math.round(match.match_score * 100)}% match`}
                                                size="small"
                                                color={match.match_score >= 0.8 ? "success" : match.match_score >= 0.6 ? "info" : "default"}
                                            />
                                            <Chip
                                                label={`${Math.round(match.skill_coverage * 100)}% skills`}
                                                size="small"
                                                variant="outlined"
                                            />
                                        </Stack>
                                        <Typography variant="caption" color="text.secondary">
                                            {match.explanation}
                                        </Typography>
                                        {match.missing_skills.length > 0 && (
                                            <Box>
                                                <Typography variant="caption" color="text.secondary" display="block">
                                                    Missing skills:
                                                </Typography>
                                                <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                                                    {match.missing_skills.map((skill) => (
                                                        <Chip key={skill} label={skill} size="small" color="warning" />
                                                    ))}
                                                </Stack>
                                            </Box>
                                        )}
                                    </Stack>
                                </Paper>
                            ))}
                        </Stack>
                    </>
                )}

                {!hasAnalysis && !hasSkillMatches && !hasGeneratedDrafts && !hasAgentMatches && (
                    <Box sx={{ textAlign: "center", py: 4 }}>
                        <Typography variant="body2" color="text.secondary">
                            Click a button above to start analyzing this task
                        </Typography>
                    </Box>
                )}
            </Stack>
        </Paper>
    );
}
