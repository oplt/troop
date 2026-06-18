import { QueryClient } from '@tanstack/react-query'

import { defaultQueryStaleTimeMs } from './queryKeys'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: defaultQueryStaleTimeMs,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})