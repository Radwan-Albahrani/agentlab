import { useNav } from '../api/queries';

/** Whether a screen is in the menu right now, so links to hidden screens aren't shown. */
export function useCanSee() {
  const { data } = useNav();
  return (path: string) => !!data && (data.system.some((s) => s.path === path) || (path === '/agents' && data.allAgents));
}
