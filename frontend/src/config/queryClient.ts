import { QueryClient } from '@tanstack/react-query'

import { defaultQueryStaleTimeMs } from './queryKeys';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: defaultQueryStaleTimeMs,
      gcTime: 15 * 60_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});
