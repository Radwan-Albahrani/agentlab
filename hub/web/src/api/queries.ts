import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';
import { api, post } from './client';
import type { AccountsPage } from './types';

/** Refetches the companion's page every second while `on`; `giveUp` runs after 30 s. */
export function useCompanionPoll(name: string, on: boolean, giveUp: () => void) {
  const qc = useQueryClient();
  const latest = useRef(giveUp);
  useEffect(() => {
    latest.current = giveUp;
  });
  useEffect(() => {
    if (!on) return;
    const poll = setInterval(() => {
      void qc.invalidateQueries({ queryKey: ['companion', name] });
    }, 1000);
    const stop = setTimeout(() => {
      latest.current();
    }, 30_000);
    return () => {
      clearInterval(poll);
      clearTimeout(stop);
    };
  }, [on, qc, name]);
}

/** Asks a companion to re-read its PRs, then polls until a list newer than `at` arrives (max 30 s); never on a timer. */
export function usePullsRefresh(name: string, at: number): [boolean, () => void] {
  const [opened] = useState(at);
  const [waiting, setWaiting] = useState<number | null>(null);
  const ask = useCallback(
    (before: number) => {
      post(`/api/companions/${name}/pulls`).then(
        () => {
          setWaiting(before);
        },
        () => {
          setWaiting(null);
        },
      );
    },
    [name],
  );
  useEffect(() => {
    ask(opened);
  }, [ask, opened]);
  const refreshing = waiting !== null && at <= waiting;
  useCompanionPoll(name, refreshing, () => {
    setWaiting(null);
  });
  return [
    refreshing,
    () => {
      ask(at);
    },
  ];
}

export const useNav = () => useQuery({ queryKey: ['nav'], queryFn: api.nav });
export const useOverview = () => useQuery({ queryKey: ['overview'], queryFn: api.overview });
export const useAgents = () => useQuery({ queryKey: ['agents'], queryFn: api.agents });
export const useAgent = (name: string) => useQuery({ queryKey: ['agent', name], queryFn: () => api.agent(name) });
export const useCompanion = (name: string) => useQuery({ queryKey: ['companion', name], queryFn: () => api.companion(name) });
export const useDevices = (name: string) => useQuery({ queryKey: ['devices', name], queryFn: () => api.devices(name) });
export const useCompanionSecrets = (name: string) =>
  useQuery({ queryKey: ['companion-secrets', name], queryFn: () => api.companionSecrets(name) });
export const useCompanionLogs = (name: string) =>
  useQuery({ queryKey: ['companion-logs', name], queryFn: () => api.companionLogs(name), refetchInterval: 5000 });
export const useServices = () => useQuery({ queryKey: ['services'], queryFn: api.services });
export const useConfigs = () => useQuery({ queryKey: ['configs'], queryFn: api.configs });
export const useStorage = () => useQuery({ queryKey: ['storage'], queryFn: api.storage });
export const useSecrets = () => useQuery({ queryKey: ['secrets'], queryFn: api.secrets });
export const useNotifications = () => useQuery({ queryKey: ['notifications'], queryFn: api.notifications });
export const useDisplay = () => useQuery({ queryKey: ['display'], queryFn: api.display });

/** Never refetches, so an open edit isn't overwritten. */
export const useConfigFile = (id: string) =>
  useQuery({ queryKey: ['config', id], queryFn: () => api.config(id), refetchInterval: false });

const signingIn = (p: AccountsPage) => [...p.ai, p.github].some((f) => f.active) || p.connectors.some((c) => c.flow?.active);

export const useAccounts = (name: string) =>
  useQuery({
    queryKey: ['accounts', name],
    queryFn: () => api.accounts(name),
    refetchInterval: (q) => (q.state.data && signingIn(q.state.data) ? 2000 : 15_000),
  });

// Revealed secret values are never kept in the cache.
const revealed = { refetchInterval: false, staleTime: 0, gcTime: 0 } as const;

export const useSecretValue = (name: string | null) =>
  useQuery({ queryKey: ['secret', name], queryFn: () => api.secretValue(name ?? ''), enabled: name !== null, ...revealed });

export const useSecretVersions = (name: string | null) =>
  useQuery({ queryKey: ['secret-versions', name], queryFn: () => api.secretVersions(name ?? ''), enabled: name !== null });

export const useEnvValue = (agent: string, key: string, shown: boolean) =>
  useQuery({ queryKey: ['env', agent, key], queryFn: () => api.envValue(agent, key), enabled: shown, ...revealed });

/** Polls a container's log tail each second until one newer than `since` arrives. */
export const useLogsTail = (name: string | null, since: number) =>
  useQuery({
    queryKey: ['logs', name, since],
    queryFn: () => api.logs(name ?? ''),
    enabled: name !== null,
    refetchInterval: (q) => ((q.state.data?.at ?? 0) >= since - 1 ? false : 1000),
    gcTime: 0,
  });

/** Toggles presenting; resolves to whether the Display screen is still reachable. */
export function useTogglePresenting() {
  const qc = useQueryClient();
  return useCallback(async () => {
    await post('/api/display/presenting', { toggle: true });
    await qc.invalidateQueries();
    const nav = await qc.query({ queryKey: ['nav'], queryFn: api.nav });
    return nav.display;
  }, [qc]);
}
