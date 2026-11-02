import type { Pull } from '../api/types';
import { arrange, grouped, matches, outdated } from './pulls';

const pull = (over: Partial<Pull>): Pull => ({
  id: 'example/app#1',
  repo: 'example/app',
  number: 1,
  title: 'feat(api): add audited MCP tools',
  url: '',
  draft: false,
  author: 'example-admin',
  avatar: '',
  labels: [{ name: 'lane:red', color: 'd73a4a' }],
  additions: 10,
  deletions: 2,
  created: '2026-11-01T10:00:00Z',
  updated: '2026-11-02T10:00:00Z',
  head: 'aaa',
  ci: 'passing',
  review: null,
  ...over,
});

describe('pull requests', () => {
  it('searches words, numbers and qualifiers', () => {
    const p = pull({});
    expect(matches(p, 'mcp')).toBe(true);
    expect(matches(p, '#1')).toBe(true);
    expect(matches(p, 'label:red author:example')).toBe(true);
    expect(matches(p, 'label:green')).toBe(false);
    expect(matches(p, 'is:draft')).toBe(false);
    expect(matches(p, 'repo:app tools')).toBe(true);
  });

  it('filters and sorts', () => {
    const items = [
      pull({ id: 'a', additions: 500, updated: '2026-11-02T09:00:00Z' }),
      pull({ id: 'b', draft: true, updated: '2026-11-02T11:00:00Z' }),
      pull({ id: 'c', review: { status: 'done', outcome: '', task: 't', head: 'aaa', at: '' } }),
    ];
    expect(arrange(items, '', 'updated', 'all').map((p) => p.id)).toEqual(['b', 'c', 'a']);
    expect(arrange(items, '', 'largest', 'all')[0]?.id).toBe('a');
    expect(arrange(items, '', 'updated', 'unreviewed').map((p) => p.id)).toEqual(['a']);
    expect(arrange(items, '', 'updated', 'reviewed').map((p) => p.id)).toEqual(['c']);
    expect(arrange(items, '', 'updated', 'drafts').map((p) => p.id)).toEqual(['b']);
  });

  it('puts your own first and notices reviews of older commits', () => {
    const { mine, others } = grouped([pull({ id: 'a' }), pull({ id: 'b', author: 'example-dev' })], 'example-admin');
    expect(mine.map((p) => p.id)).toEqual(['a']);
    expect(others.map((p) => p.id)).toEqual(['b']);
    const review = { status: 'done' as const, outcome: '', task: 't', head: 'old', at: '' };
    expect(outdated(pull({ review }))).toBe(true);
    expect(outdated(pull({ review: { ...review, head: 'aaa' } }))).toBe(false);
  });
});
