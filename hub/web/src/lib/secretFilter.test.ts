import type { Secret } from '../api/types';
import { filterSecrets, kindCounts, users, type SecretFilter } from './secretFilter';

const secret = (over: Partial<Secret>): Secret => ({
  name: 'x.txt',
  label: '',
  used_by: [],
  about: '',
  how: '',
  modified: 0,
  versions: 0,
  effect: '',
  kinds: ['read'],
  ...over,
});

const items = [
  secret({ name: 'scout-bot-token.txt', label: 'Scout · Slack bot token', used_by: ['Scout'], kinds: ['restart'] }),
  secret({ name: 'scout-agent-key.txt', used_by: ['Scout', 'admin agent'], kinds: ['copy', 'restart'] }),
  secret({ name: 'grafana-api-key.txt', used_by: ['dashboards'], about: 'An API key for Grafana.' }),
  secret({ name: 'notes.txt', kinds: ['unmapped'] }),
];
const none: SecretFilter = { q: '', kind: 'all', usedBy: '' };
const names = (f: SecretFilter) => filterSecrets(items, f).map((s) => s.name);

test('search matches label, file name, users and the about text, ignoring case', () => {
  expect(names({ ...none, q: 'SLACK' })).toEqual(['scout-bot-token.txt']);
  expect(names({ ...none, q: 'agent-key' })).toEqual(['scout-agent-key.txt']);
  expect(names({ ...none, q: 'admin' })).toEqual(['scout-agent-key.txt']);
  expect(names({ ...none, q: 'grafana.' })).toEqual(['grafana-api-key.txt']);
  expect(names({ ...none, q: '  ' })).toHaveLength(4);
});

test('kind and "used by" filters combine with the search', () => {
  expect(names({ ...none, kind: 'restart' })).toEqual(['scout-bot-token.txt', 'scout-agent-key.txt']);
  expect(names({ ...none, kind: 'restart', usedBy: 'admin agent' })).toEqual(['scout-agent-key.txt']);
  expect(names({ ...none, kind: 'unmapped', q: 'scout' })).toEqual([]);
});

test('counts follow the other filters', () => {
  expect(kindCounts(items, none)).toEqual({ all: 4, restart: 2, copy: 1, read: 1, unmapped: 1 });
  expect(kindCounts(items, { ...none, usedBy: 'Scout' })).toEqual({ all: 2, restart: 2, copy: 1, read: 0, unmapped: 0 });
  expect(users(items, none)).toEqual([
    { name: 'Scout', count: 2 },
    { name: 'admin agent', count: 1 },
    { name: 'dashboards', count: 1 },
  ]);
  expect(users(items, { ...none, kind: 'read' })).toEqual([{ name: 'dashboards', count: 1 }]);
});
