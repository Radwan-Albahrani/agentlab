import type { Pull } from '../api/types';

export type PullSort = 'updated' | 'created' | 'smallest' | 'largest';
export type PullFilter = 'all' | 'unreviewed' | 'reviewed' | 'drafts';

export const SORTS: { value: PullSort; label: string }[] = [
  { value: 'updated', label: 'Recently updated' },
  { value: 'created', label: 'Newest' },
  { value: 'smallest', label: 'Smallest change' },
  { value: 'largest', label: 'Largest change' },
];

export const FILTERS: { value: PullFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'unreviewed', label: 'Not reviewed' },
  { value: 'reviewed', label: 'Reviewed' },
  { value: 'drafts', label: 'Drafts' },
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
  const kept = items.filter(
    (p) =>
      matches(p, query) &&
      (filter === 'all' ||
        (filter === 'drafts' && p.draft) ||
        (filter === 'reviewed' && !!p.review) ||
        (filter === 'unreviewed' && !p.review && !p.draft)),
  );
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
