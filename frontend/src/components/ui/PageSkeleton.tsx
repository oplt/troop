import { Box, Skeleton, Stack } from "@mui/material";

export type PageSkeletonVariant = "browse" | "form" | "inspector" | "canvas";

type PageSkeletonProps = {
    variant?: PageSkeletonVariant;
};

/** Layout-aware Suspense/route loading placeholder (not a spinner). */
export function PageSkeleton({ variant = "browse" }: PageSkeletonProps) {
    if (variant === "form") {
        return (
            <Box sx={{ px: { xs: 2, md: 3 }, py: { xs: 3, md: 4 }, maxWidth: 720 }}>
                <Stack spacing={2}>
                    <Skeleton variant="text" width="40%" height={40} />
                    <Skeleton variant="text" width="70%" height={24} />
                    <Skeleton variant="rounded" height={56} sx={{ borderRadius: 1 }} />
                    <Skeleton variant="rounded" height={56} sx={{ borderRadius: 1 }} />
                    <Skeleton variant="rounded" height={120} sx={{ borderRadius: 1 }} />
                    <Skeleton variant="rounded" width={160} height={40} sx={{ borderRadius: 1 }} />
                </Stack>
            </Box>
        );
    }

    if (variant === "inspector") {
        return (
            <Box sx={{ px: { xs: 2, md: 3 }, py: { xs: 3, md: 4 } }}>
                <Stack spacing={2}>
                    <Skeleton variant="rounded" height={88} sx={{ borderRadius: 1 }} />
                    <Skeleton variant="rounded" height={48} sx={{ borderRadius: 1 }} />
                    <Skeleton variant="rounded" height={360} sx={{ borderRadius: 1 }} />
                </Stack>
            </Box>
        );
    }

    if (variant === "canvas") {
        return (
            <Box sx={{ px: { xs: 2, md: 3 }, py: { xs: 3, md: 4 } }}>
                <Stack spacing={2}>
                    <Skeleton variant="rounded" height={48} sx={{ borderRadius: 1 }} />
                    <Box
                        sx={{
                            display: "grid",
                            gridTemplateColumns: { xs: "1fr", lg: "240px minmax(0, 1fr)" },
                            gap: 2,
                        }}
                    >
                        <Skeleton variant="rounded" height={420} sx={{ borderRadius: 1 }} />
                        <Skeleton variant="rounded" height={520} sx={{ borderRadius: 1 }} />
                    </Box>
                </Stack>
            </Box>
        );
    }

    return (
        <Box sx={{ px: { xs: 2, md: 3 }, py: { xs: 3, md: 4 } }}>
            <Stack spacing={3}>
                <Stack spacing={1}>
                    <Skeleton variant="text" width="28%" height={36} />
                    <Skeleton variant="text" width="55%" height={22} />
                </Stack>
                <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                    <Skeleton variant="rounded" height={120} sx={{ borderRadius: 1, flex: 1 }} />
                    <Skeleton variant="rounded" height={120} sx={{ borderRadius: 1, flex: 1 }} />
                    <Skeleton variant="rounded" height={120} sx={{ borderRadius: 1, flex: 1 }} />
                </Stack>
                <Skeleton variant="rounded" height={48} sx={{ borderRadius: 1 }} />
                <Skeleton variant="rounded" height={280} sx={{ borderRadius: 1 }} />
            </Stack>
        </Box>
    );
}
