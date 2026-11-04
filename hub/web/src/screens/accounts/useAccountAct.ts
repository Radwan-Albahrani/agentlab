import { useAct } from '../../ui/feedback';

export function useAccountAct(agent: string) {
  const act = useAct();
  return (body: Record<string, unknown>, confirm?: string) =>
    act(`/api/agents/${agent}/accounts/act`, body, { confirm, quiet: true });
}
