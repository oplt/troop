import { Stack, TextField, Typography } from "@mui/material";

type AgentMarkdownEditorProps = {
    markdown: string;
    onChange: (value: string) => void;
};

export function AgentMarkdownEditor({ markdown, onChange }: AgentMarkdownEditorProps) {
    return (
        <Stack spacing={2}>
            <Typography color="text.secondary">
                Markdown is the portable instruction source. Structured fields above are stored alongside it and
                override matching frontmatter.
            </Typography>
            <TextField
                label="Agent markdown"
                value={markdown}
                onChange={(event) => onChange(event.target.value)}
                multiline
                minRows={24}
                fullWidth
                sx={{ "& textarea": { fontFamily: "monospace", fontSize: 13 } }}
            />
        </Stack>
    );
}
