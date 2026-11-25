import type { Pull } from '../api/types';

export type PullSort = 'updated' | 'created' | 'smallest' | 'largest';
/** Where a PR stands, one answer each: what the filter counts and narrows by. */
export type Outcome = 'blocking' | 'findings' | 'clean' | 'reviewing' | 'failed' | 'unreviewed' | 'draft';
export type PullFilter = 'all' | Outcome;

const BUSY = new Set(['queued', 'working', 'waiting', 'paused']); // paused: T3 resumes it after the usage limit

export function outcomeOf(p: Pull): Outcome {
  const r = p.review;
  if (!r) return p.draft ? 'draft' : 'unreviewed';
  if (BUSY.has(r.status)) return 'reviewing';
  if (r.status !== 'done') return 'failed';
  if (r.counts?.blocking || r.counts?.open_blocking) return 'blocking';
  if (r.counts && (r.counts.findings || r.counts.open)) return 'findings';
  return 'clean';
}

export const SORTS: { value: PullSort; label: string }[] = [
  { value: 'updated', label: 'Recently updated' },
  { value: 'created', label: 'Newest' },
  { value: 'smallest', label: 'Smallest change' },
  { value: 'largest', label: 'Largest change' },
];

export const FILTERS: { value: PullFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'blocking', label: 'Blocking' },
  { value: 'findings', label: 'With findings' },
  { value: 'clean', label: 'Clean' },
  { value: 'reviewing', label: 'In review' },
  { value: 'failed', label: 'Review failed' },
  { value: 'unreviewed', label: 'Not reviewed' },
  { value: 'draft', label: 'Drafts' },
];

const size = (p: Pull) => p.additions + p.deletions;

/** Free words match the number, title, author or repo; `label:`, `author:`, `repo:` and `is:draft` narrow it. */
export function matches(p: Pull, query: string): boolean {
  return query
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .every((word) => {
      const [k, v = ''] = word.includes(':') ? word.split(/:(.*)/) : ['', word];
      if (k === 'label') return p.labels.some((l) => l.name.toLowerCase().includes(v));
      if (k === 'author') return p.author.toLowerCase().includes(v);
      if (k === 'repo') return p.repo.toLowerCase().includes(v);
      if (k === 'is') return v === 'draft' ? p.draft : v === 'open' ? !p.draft : true;
      const w = word.replace(/^#/, '');
      return [String(p.number), p.title, p.author, p.repo].some((x) => x.toLowerCase().includes(w));
    });
}

export function arrange(items: Pull[], query: string, sort: PullSort, filter: PullFilter): Pull[] {
  const kept = items.filter((p) => matches(p, query) && (filter === 'all' || outcomeOf(p) === filter));
  const by: Record<PullSort, (a: Pull, b: Pull) => number> = {
    updated: (a, b) => b.updated.localeCompare(a.updated),
    created: (a, b) => b.created.localeCompare(a.created),
    smallest: (a, b) => size(a) - size(b),
    largest: (a, b) => size(b) - size(a),
  };
  return [...kept].sort(by[sort]);
}

export function grouped(items: Pull[], me: string): { mine: Pull[]; others: Pull[] } {
  const own = (p: Pull) => !!me && p.author.toLowerCase() === me.toLowerCase();
  return { mine: items.filter(own), others: items.filter((p) => !own(p)) };
}

/** The review is of an older commit than the PR's head. */
export const outdated = (p: Pull) => !!p.review?.head && p.review.head !== p.head && p.review.status === 'done';
