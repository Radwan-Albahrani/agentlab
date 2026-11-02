import type { Secret, SecretKind } from '../api/types';

export type KindFilter = 'all' | SecretKind;

export interface SecretFilter {
  q: string;
  kind: KindFilter;
  usedBy: string; // '' = anyone
}

export const KIND_LABELS: Record<KindFilter, string> = {
  all: 'All',
  restart: 'Restarts a service',
  copy: 'Copied into an agent',
  read: 'Read when used',
  unmapped: 'Not mapped',
};

const KINDS = Object.keys(KIND_LABELS) as KindFilter[];

export const isKind = (v: string | null): v is KindFilter => KINDS.includes(v as KindFilter);

const matchesText = (s: Secret, q: string) =>
  !q || [s.label, s.name, s.about, ...s.used_by].some((field) => field.toLowerCase().includes(q.toLowerCase()));

const matchesKind = (s: Secret, kind: KindFilter) => kind === 'all' || s.kinds.includes(kind);

const matchesUser = (s: Secret, usedBy: string) => !usedBy || s.used_by.includes(usedBy);

export function filterSecrets(items: Secret[], f: SecretFilter): Secret[] {
  const q = f.q.trim();
  return items.filter((s) => matchesText(s, q) && matchesKind(s, f.kind) && matchesUser(s, f.usedBy));
}

/** How many secrets each kind option would show, given the search and the "used by" choice. */
export function kindCounts(items: Secret[], f: SecretFilter): Record<KindFilter, number> {
  const rest = filterSecrets(items, { ...f, kind: 'all' });
  return Object.fromEntries(KINDS.map((k) => [k, rest.filter((s) => matchesKind(s, k)).length])) as Record<KindFilter, number>;
}

/** Everyone that uses at least one secret, most used first, with counts given the search and kind. */
export function users(items: Secret[], f: SecretFilter): { name: string; count: number }[] {
  const rest = filterSecrets(items, { ...f, usedBy: '' });
  const counts = new Map<string, number>();
  for (const s of rest) for (const u of s.used_by) counts.set(u, (counts.get(u) ?? 0) + 1);
  return [...counts].map(([name, count]) => ({ name, count })).sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
}
