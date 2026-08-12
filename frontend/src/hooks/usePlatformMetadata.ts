import { useQuery } from "@tanstack/react-query";

import { getPlatformMetadata } from "../api/platform";
import { queryKeys } from "../config/queryKeys";
import { queryPolicies } from "../config/queryPolicies";

export function usePlatformMetadata() {
    return useQuery({
        queryKey: queryKeys.platform.metadata,
        queryFn: getPlatformMetadata,
        ...queryPolicies.reference,
    });
}
