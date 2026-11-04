import type * as T from './types';

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<R>(url: string, init?: RequestInit): Promise<R> {
  const r = await fetch(url, init);
  let body: { error?: string } & Record<string, unknown> = {};
  try {
    body = (await r.json()) as typeof body;
  } catch {
    /* non-JSON error page */
  }
  if (!r.ok || body.ok === false) throw new ApiError(body.error || `HTTP ${r.status}`, r.status);
  return body as R;
}

export const get = <R>(url: string) => request<R>(url);

/** POST a JSON action; resolves to the toast text. */
export async function post(url: string, body: Record<string, unknown> = {}): Promise<string> {
  const r = await request<{ message?: string }>(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return r.message || 'Done';
}

/** POST and return the server's data instead of a toast text. */
export async function postFor<R>(url: string, body: Record<string, unknown> = {}): Promise<R> {
  const r = await request<{ message: R }>(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return r.message;
}

const q = (params: Record<string, string>) => new URLSearchParams(params).toString();

export const api = {
  nav: () => get<T.Nav>('/api/nav'),
  overview: () => get<T.Overview>('/api/overview'),
  agents: () => get<T.Agents>('/api/agents'),
  agent: (name: string) => get<T.AgentPage>(`/api/agents/${name}`),
  accounts: (name: string) => get<T.AccountsPage>(`/api/agents/${name}/accounts`),
  envValue: (name: string, key: string) =>
    get<{ value: string | null }>(`/api/agents/${name}/accounts/env-value?${q({ k: key })}`),
  devices: (name: string) => get<{ devices: T.Device[] }>(`/api/agents/${name}/devices`),
  pair: (name: string, kind: 'browser' | 'app', label = '') => postFor<T.PairLink>(`/api/agents/${name}/pair`, { kind, label }),
  companion: (name: string) => get<T.Companion>(`/api/companions/${name}`),
  companionSecrets: (name: string) => get<T.CompanionSecrets>(`/api/companions/${name}/secrets`),
  companionSecretValue: (name: string, file: string) =>
    get<{ value: string }>(`/api/companions/${name}/secrets/value?${q({ file })}`),
  companionLogs: (name: string) => get<{ text: string; at: number }>(`/api/companions/${name}/logs`),
  services: () => get<T.Services>('/api/services'),
  logs: (name: string) => get<{ text: string; at: number }>(`/api/logs?${q({ name })}`),
  configs: () => get<T.Configs>('/api/configs'),
  config: (id: string) => get<T.ConfigFile>(`/api/config?${q({ id })}`),
  storage: () => get<T.Storage>('/api/storage'),
  secrets: () => get<T.Secrets>('/api/secrets'),
  secretValue: (name: string) => get<{ value: string }>(`/api/secrets/value?${q({ name })}`),
  secretVersions: (name: string) => get<{ versions: string[] }>(`/api/secrets/versions?${q({ name })}`),
  notifications: () => get<T.Notifications>('/api/notifications'),
  display: () => get<T.DisplaySettings>('/api/display'),
};
