import { useQuery } from "@tanstack/react-query";
import { api } from "../services/api";
export function useData<T>(
  key: string,
  path: string,
  interval?: number,
  enabled = true,
) {
  return useQuery<T>({
    queryKey: [key, path],
    queryFn: async () => (await api.get(path)).data,
    refetchInterval: interval,
    retry: 1,
    enabled,
  });
}
