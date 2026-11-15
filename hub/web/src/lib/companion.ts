import type { Event, Poll, Task } from '../api/types';
import { clock, duration, plural } from './format';

export type TaskFilter = 'all' | 'errand' | 'task' | 'done' | 'failed';

export const TASK_FILTERS: { value: TaskFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'errand', label: 'Errands' },
  { value: 'task', label: 'Tasks' },
  { value: 'done', label: 'Done' },
  { value: 'failed', label: 'Failed' },
];

export function filterTasks(tasks: Task[], f: TaskFilter): Task[] {
  if (f === 'all') return tasks;
  if (f === 'errand' || f === 'task') return tasks.filter((t) => t.kind === f);
  return tasks.filter((t) => t.status === f);
}

/** Until now while still going (an earlier turn's end doesn't count); '' for old tasks without an end time. */
export function taskAge(t: Task, now = Date.now() / 1000): string {
  const going = t.status === 'working' || t.status === 'waiting' || t.status === 'paused';
  if (!t.startedAt || (!t.endedAt && !going)) return '';
  return duration((going ? now : (t.endedAt ?? now)) - t.startedAt);
}

/** Slack text in pieces: plain strings and {url, label} for its <url|label> and <url> links. */
export function slackParts(s: string): (string | { url: string; label: string })[] {
  const out: (string | { url: string; label: string })[] = [];
  let at = 0;
  for (const m of s.matchAll(/<(https?:\/\/[^|>\s]+)(?:\|([^>]*))?>/g)) {
    if (m.index > at) out.push(s.slice(at, m.index));
    const url = m[1] ?? '';
    out.push({ url, label: m[2] || url });
    at = m.index + m[0].length;
  }
  if (at < s.length) out.push(s.slice(at));
  return out;
}

/** Slack text with links reduced to their labels, for tooltips. */
export const slackPlain = (s: string) =>
  slackParts(s)
    .map((p) => (typeof p === 'string' ? p : p.label))
    .join('');

/** Who asked: '' is you; a task's starter, an errand's requester. */
export const ME = '';
export function askers(tasks: Task[]): { value: string; label: string }[] {
  const n = new Map<string, number>();
  for (const t of tasks) n.set(t.requester || ME, (n.get(t.requester || ME) ?? 0) + 1);
  const others = [...n.keys()].filter((k) => k !== ME).sort((a, b) => a.localeCompare(b));
  return [
    { value: '*', label: `Anyone · ${tasks.length}` },
    ...(n.has(ME) ? [{ value: 'me', label: `You · ${n.get(ME)}` }] : []),
    ...others.map((k) => ({ value: `@${k}`, label: `${k} · ${n.get(k)}` })),
  ];
}
export function askedBy(tasks: Task[], who: string): Task[] {
  if (who === '*') return tasks;
  const want = who === 'me' ? ME : who.slice(1);
  return tasks.filter((t) => (t.requester || ME) === want);
}

/** An errand is done for someone; a task or review was started by them (or by you). */
export function taskWho(t: Task): string {
  return `${t.kind === 'errand' ? 'for' : 'started by'} ${t.requester || 'you'}`;
}

const WEEK = 7 * 86400;

export function weekStats(tasks: Task[], sent: Event[], now = Date.now() / 1000) {
  const week = tasks.filter((t) => now - t.startedAt < WEEK);
  return {
    waiting: tasks.filter((t) => t.status === 'waiting').length,
    working: tasks.filter((t) => t.status === 'working').length,
    paused: tasks.filter((t) => t.status === 'paused').length,
    taken: week.length,
    errands: week.filter((t) => t.kind === 'errand').length,
    plainTasks: week.filter((t) => t.kind === 'task').length,
    done: week.filter((t) => t.status === 'done').length,
    failed: week.filter((t) => t.status === 'failed').length,
    sent: sent.length,
    people: new Set(sent.map((e) => e.to).filter(Boolean)).size,
  };
}

export const WAITING: Record<string, { label: string; icon: string }> = {
  approval: { label: 'Approve a change', icon: 'alert' },
  send: { label: 'Send the reply', icon: 'send' },
  post: { label: 'Check a post', icon: 'send' },
  login: { label: 'Send a login', icon: 'key' },
  answer: { label: 'Answer a question', icon: 'chat' },
};

export const TASK_PILL: Record<string, [string, 'info' | 'warn' | 'ok' | 'bad' | 'idle']> = {
  working: ['Working', 'info'],
  waiting: ['Needs you', 'warn'],
  paused: ['Paused', 'warn'],
  done: ['Done', 'ok'],
  failed: ['Failed', 'bad'],
  stopped: ['Stopped', 'idle'],
};

/** "resumes 1:50 AM" (with the day when it's further off) for work paused by a usage limit. */
export function resumesLabel(at: number | null | undefined, now = Date.now() / 1000): string {
  if (!at) return 'resumes when the limit resets';
  const time = new Date(at * 1000).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
  return `resumes ${Math.abs(at - now) > 86400 ? clock(at) : time}`;
}

export const STATE_PILL: Record<string, [string, 'ok' | 'warn' | 'bad']> = {
  live: ['Live', 'ok'],
  disconnected: ['Slack disconnected', 'warn'],
  offline: ['Offline', 'bad'],
  unconfigured: ['Not set up', 'warn'],
};

const voterCount = (p: Poll) => new Set(p.options.flatMap((o) => o.voters.map((v) => v.name))).size;

/** "Leading: A, B · 2 votes each · 3 people voted · closes Thu 2:00 PM" (or the winner once closed). */
export function pollSummary(p: Poll): string {
  const people = voterCount(p);
  const when = p.open ? `closes ${clock(p.closes)}` : `closed ${clock(p.closed ?? p.closes)}`;
  if (!people) return `No votes yet · ${when}`;
  const best = Math.max(...p.options.map((o) => o.votes));
  const top = p.options.filter((o) => o.votes === best).map((o) => o.label);
  const lead =
    top.length === 1
      ? `${p.open ? 'Leading' : 'Winner'}: ${top[0]} · ${plural(best, 'vote')}`
      : `${p.open ? 'Leading' : 'Tie'}: ${top.join(', ')} · ${plural(best, 'vote')} each`;
  return `${lead} · ${plural(people, 'person', 'people')} voted · ${when}`;
}
