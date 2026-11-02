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

/** How long a task ran; empty for ones that finished before end times were recorded. */
/** How long a task has run: until now while it is still going (an earlier turn's end does not count), else until it ended. */
export function taskAge(t: Task, now = Date.now() / 1000): string {
  const going = t.status === 'working' || t.status === 'waiting';
  if (!t.startedAt || (!t.endedAt && !going)) return '';
  return duration((going ? now : (t.endedAt ?? now)) - t.startedAt);
}

const WEEK = 7 * 86400;

export function weekStats(tasks: Task[], sent: Event[], now = Date.now() / 1000) {
  const week = tasks.filter((t) => now - t.startedAt < WEEK);
  return {
    waiting: tasks.filter((t) => t.status === 'waiting').length,
    working: tasks.filter((t) => t.status === 'working').length,
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
  done: ['Done', 'ok'],
  failed: ['Failed', 'bad'],
  stopped: ['Stopped', 'idle'],
};

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
