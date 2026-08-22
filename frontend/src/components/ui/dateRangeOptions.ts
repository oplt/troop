export const ANALYTICS_DAY_OPTIONS = [7, 14, 30, 90] as const;
export type AnalyticsDays = (typeof ANALYTICS_DAY_OPTIONS)[number];
