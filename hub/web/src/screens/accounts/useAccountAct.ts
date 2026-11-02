import { useAct } from '../../ui/feedback';

/** Every button on the Accounts screen is one action on the agent's Accounts app. */
export function useAccountAct(agent: string) {
  const act = useAct();
  return (body: Record<string, unknown>, confirm?: string) =>
    act(`/api/agents/${agent}/accounts/act`, body, { confirm, quiet: true });
}
