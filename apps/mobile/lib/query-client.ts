import { QueryClient } from "@tanstack/react-query";

// App-wide React Query client — all server state flows through this
// (see plans/01-architecture.md). Provided once at the root layout.
export const queryClient = new QueryClient();
