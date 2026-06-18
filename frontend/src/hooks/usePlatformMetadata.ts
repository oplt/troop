import { useQuery } from "@tanstack/react-query";

import { getPlatformMetadata } from "../api/platform";
import { defaultQueryStaleTimeMs, queryKeys } from "../config/queryKeys";

export function usePlatformMetadata() {
    return useQuery({
        queryKey: queryKeys.platform.metadata,
        queryFn: getPlatformMetadata,
        staleTime: defaultQueryStaleTimeMs,
    });
}
