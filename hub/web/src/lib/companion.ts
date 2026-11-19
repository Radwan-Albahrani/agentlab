import type { CaseItem, Event, ItemState, Phase, Poll, Route, RouteBy, Task } from '../api/types';
import { clock, duration, plural } from './format';

type Tone = 'info' | 'warn' | 'ok' | 'bad' | 'idle';

/** Why a chat started in its project (companion/bot/projects.py BY). */
export const ROUTE_BY: Record<RouteBy, string> = {
  repo: "the PR's repository",
  named: 'named in the ask',
  channel: 'the channel',
  thread: 'mentioned in the thread',
  topic: 'by topic',
  default: 'the default project',
  checkout: 'a fresh checkout of the repository',
  earlier: 'chosen before routes were recorded',
};

/** "netzero-platform/apps/node-api · named in the ask" */
export const routeLine = (r: Route) => `${r.project.replace(/^\/workspace\//, '')} · ${ROUTE_BY[r.by]}`;

/** Where a task stands (companion/bot/machine.py), as a pill. */
export const PHASE_PILL: Record<Phase, [string, Tone]> = {
  working: ['Working', 'info'],
  waiting_owner: ['Needs you', 'warn'],
  waiting_answer: ['Asked a question', 'warn'],
  paused: ['Paused', 'warn'],
  answered: ['Answered', 'ok'],
  nothing_to_do: ['Nothing to do', 'ok'],
  stopped: ['Stopped', 'idle'],
  failed: ['Failed', 'bad'],
};

/** What became of an item (companion/bot/ledger.py), as a pill. */
export const ITEM_PILL: Record<ItemState, [string, Tone]> = {
  received: ['Received', 'idle'],
  awaiting_owner: ['Waiting for you', 'warn'],
  approved: ['Approved', 'ok'],
  sent: ['Sent', 'ok'],
  silent: ['Nothing to say', 'idle'],
  applied: ['Applied', 'ok'],
  refused: ['Refused', 'bad'],
  rejected: ['Rejected by you', 'idle'],
  replaced: ['Replaced', 'idle'],
  withdrawn: ['Withdrawn', 'idle'],
  failed: ['Failed', 'bad'],
  dry_run: ['Dry run: not sent', 'idle'],
  lost: ['Lost', 'bad'],
};

/** "received 9:58 AM → waiting for you → approved 10:02 AM": how an item got where it is. */
export const itemHistory = (it: CaseItem) =>
  it.history
    .map(([s, at]) => {
      const time = new Date(at * 1000).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
      return `${ITEM_PILL[s][0].toLowerCase()} ${time}`;
    })
    .join(' → ');

/** A case: a conversation someone other than you has with the companion (a colleague, or an errand's requester). */
export const casesOf = (tasks: Task[]) => tasks.filter((t) => t.party !== 'owner');

export const waitingOnYou = (t: Task) => t.items.filter((i) => i.state === 'awaiting_owner');

export const needsYou = (t: Task) => t.phase === 'waiting_owner' || t.phase === 'waiting_answer' || waitingOnYou(t).length > 0;

const OPEN: Phase[] = ['working', 'waiting_owner', 'waiting_answer', 'paused'];
export const isOpen = (t: Task) => (t.phase ? OPEN.includes(t.phase) : false) || needsYou(t);

export type CaseFilter = 'you' | 'open' | 'all';
export function filterCases(cases: Task[], f: CaseFilter): Task[] {
  return f === 'you' ? cases.filter(needsYou) : f === 'open' ? cases.filter(isOpen) : cases;
}

/** How a message item reads: who to whom, and whether it is your private exchange with the companion. */
export interface Line {
  from: string;
  to: string;
  side: 'theirs' | 'ours' | 'private';
}

/** null for items that are decisions or changes rather than messages (approvals, logins, edits, poll changes). */
export function lineOf(it: CaseItem, who: string, me: string): Line | null {
  if (it.kind === 'in')
    return it.private ? { from: 'You', to: me, side: 'private' } : { from: it.label || who, to: me, side: 'theirs' };
  if (it.kind === 'final')
    return it.to === 'case' ? { from: me, to: 'you', side: 'private' } : { from: me, to: it.label || who, side: 'ours' };
  if (it.kind !== 'message') return null;
  if (it.to === 'owner') return { from: me, to: 'you', side: 'private' };
  if (it.to === 'thread') return { from: me, to: 'the thread', side: 'ours' };
  return { from: me, to: it.label || it.to || 'nobody named', side: 'ours' };
}

export type TaskFilter = 'all' | 'errand' | 'task' | 'review' | 'done' | 'failed';

export const TASK_FILTERS: { value: TaskFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'errand', label: 'Errands' },
  { value: 'task', label: 'Tasks' },
  { value: 'review', label: 'Reviews' },
  { value: 'done', label: 'Done' },
  { value: 'failed', label: 'Failed' },
];

export function filterTasks(tasks: Task[], f: TaskFilter): Task[] {
  if (f === 'all') return tasks;
  if (f === 'errand' || f === 'task' || f === 'review') return tasks.filter((t) => t.kind === f);
  return tasks.filter((t) => t.status === f);
}

/** Until now while still going (an earlier turn's end doesn't count); '' for old tasks without an end time. */
export function taskAge(t: Task, now = Date.now() / 1000): string {
  const going = t.status === 'working' || t.status === 'waiting' || t.status === 'paused';
  if (!t.startedAt || (!t.endedAt && !going)) return '';
  return duration((going ? now : (t.endedAt ?? now)) - t.startedAt);
}

export type SentTo = 'all' | 'person' | 'channel' | 'github';
export const SENT_FILTERS: { value: SentTo; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'person', label: 'To people' },
  { value: 'channel', label: 'In channels' },
  { value: 'github', label: 'On GitHub' },
];

/** Where a delivery went: a #channel, a pull request (owner/repo#12 or repo#12), or else a person's DM. */
export function sentTo(e: Event): Exclude<SentTo, 'all'> {
  const to = e.to ?? '';
  if (/^[\w.-]+(\/[\w.-]+)?#\d+$/.test(to)) return 'github';
  if (!to || to.startsWith('#')) return 'channel';
  return 'person';
}

export interface Delivery {
  where: Exclude<SentTo, 'all'>;
  to: string;
  link: string;
  what: string;
  note: string;
}

const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/** A delivery read at a glance: where it went, what it was, and a line about it, without the destination said twice. */
export function delivery(e: Event): Delivery {
  const where = sentTo(e);
  const raw = e.to ?? '';
  const pr = /^(?:([\w.-]+)\/)?([\w.-]+)#(\d+)$/.exec(raw);
  const to = where === 'github' && pr ? `${pr[2]}#${pr[3]}` : raw.replace(/ by DM$/, '') || 'a channel';
  const link = pr?.[1] ? `https://github.com/${pr[1]}/${pr[2]}/pull/${pr[3]}` : '';
  const title = raw ? e.title.replace(new RegExp(`\\s+(?:to|in|of|for)\\s+${escape(raw)}`), '') : e.title;
  const [what = title, summary = ''] = title.split(/:\s+(.*)/s);
  const detail =
    slackPlain(e.detail ?? '')
      .split('\n')
      .find((l) => l.trim()) ?? '';
  return { where, to, link, what, note: detail.trim() || summary };
}

/** Today, Yesterday, or the date, for grouping deliveries by day. */
export function dayLabel(t: number, now = Date.now() / 1000): string {
  const day = (s: number) => new Date(s * 1000).toDateString();
  if (day(t) === day(now)) return 'Today';
  if (day(t) === day(now - 86400)) return 'Yesterday';
  return new Date(t * 1000).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });
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

/** Who and how: an errand is done for someone; a task or review was started by someone (or you), somewhere, maybe
 * after an approval; a review others asked for too names them. */
export function taskWho(t: Task): string {
  const via = t.via ? ` ${t.via}` : '';
  const approved = t.approvedBy ? ` · approved by ${t.approvedBy}` : '';
  if (t.kind === 'errand') return `for ${t.requester || 'you'}${t.via ? ` · ${t.via}` : ''}${approved}`;
  const by = t.startedBy || (t.via === undefined || t.via === '' ? t.requester : '') || 'you';
  const also = t.requester && t.requester !== by ? ` · for ${t.requester}` : '';
  return `started by ${by}${via}${approved}${also}`;
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
