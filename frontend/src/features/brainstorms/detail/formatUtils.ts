export function agentInitials(value: string) {
    return value
        .split(" ")
        .map((part) => part[0] ?? "")
        .join("")
        .slice(0, 2)
        .toUpperCase();
}

export function groupMessagesByRound<T extends { round_number: number }>(messages: T[]) {
    const grouped = new Map<number, T[]>();
    messages.forEach((message) => {
        const bucket = grouped.get(message.round_number) ?? [];
        bucket.push(message);
        grouped.set(message.round_number, bucket);
    });
    return [...grouped.entries()].sort((left, right) => left[0] - right[0]);
}

export function consensusChipColor(status: string): "success" | "warning" | "default" {
    if (status === "consensus" || status === "soft_consensus") return "success";
    if (status === "loop_detected" || status === "conflict") return "warning";
    return "default";
}
