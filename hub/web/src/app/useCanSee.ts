import { useNav } from '../api/queries';

export function useCanSee() {
  const { data } = useNav();
  return (path: string) => !!data && (data.system.some((s) => s.path === path) || (path === '/agents' && data.allAgents));
}
